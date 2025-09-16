import json
import logging
import os
import re
import uuid
from typing import Dict, Any, List, Optional

try:
    from .genai_provider import OpenAIProvider
except Exception:
    OpenAIProvider = None

from .config import OPENAI_API_KEY
from .aws_fetcher_async import AWSResourceFetcher
from .permissions import get_department_limits, can_create_resource, check_environment_access

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

OS_WORDS = {
    "ubuntu": "ubuntu",
    "ubuntu22": "ubuntu22", 
    "amazon-linux": "amazon-linux",
    "amazon linux": "amazon-linux",
    "windows": "windows",
    "centos": "centos",
}

ENV_WORDS = {"dev", "qa", "prod"}

DEFAULT_SG_RULES = {
    "ingress": [
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "ranges": ["0.0.0.0/0"], "description": "SSH"},
        {"protocol": "tcp", "from_port": 80, "to_port": 80, "ranges": ["0.0.0.0/0"], "description": "HTTP"},
        {"protocol": "tcp", "from_port": 443, "to_port": 443, "ranges": ["0.0.0.0/0"], "description": "HTTPS"}
    ],
    "egress": [
        {"protocol": "-1", "from_port": -1, "to_port": -1, "ranges": ["0.0.0.0/0"], "description": "All outbound"}
    ]
}


class LLMProcessor:
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}
        self.user_context: Dict[str, Dict] = {}
        if OpenAIProvider and OPENAI_API_KEY:
            try:
                self.provider = OpenAIProvider(OPENAI_API_KEY)
            except Exception as e:
                logger.warning("OpenAIProvider init failed: %s", e)
                self.provider = None
        else:
            self.provider = None

    def _normalize_input(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        return text.lower().strip()

    def _normalize_env_input(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        t = self._normalize_input(text)
        if t in {"dev", "development"}:
            return "dev"
        if t in {"qa", "test", "testing"}:
            return "qa"
        if t in {"prod", "production"}:
            return "prod"
        return None

    def _normalize_region_input(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        t = self._normalize_input(text)
        t = t.replace("_", "-")
        t = t.replace("useast1", "us-east-1").replace("useast-1", "us-east-1").replace("us-east1", "us-east-1")
        t = re.sub(r"^([a-z]{2})([a-z]+)(\d)$", lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}", t)
        if re.match(r"^[a-z]{2}-[a-z]+-\d+$", t):
            return t
        return None

    async def process_user_message(self, user_email: str, message: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        try:
            msg = (message or "").strip()
            if user_email not in self.conversations:
                self.conversations[user_email] = []
                self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}

            if msg == "CLEAR_CONVERSATION" or self._normalize_input(msg) in {"cancel", "stop", "abort"}:
                self.conversations[user_email] = []
                self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
                return {"message": "Cancelled. Ready for new request.", "buttons": [], "show_text_input": True}

            self.conversations[user_email].append({"role": "user", "content": msg})
            state = self.user_context[user_email]
            step = state.get("step", "initial")

            handlers = {
                "initial": self._handle_initial,
                "ask_environment": self._handle_environment_selection,
                "ask_instance_type": self._handle_instance_type,
                "ask_os": self._handle_operating_system,
                "ask_storage": self._handle_storage,
                "ask_region": self._handle_region,
                "awaiting_technical_approval": self._handle_technical_approval_response,
                "ask_resource_mode": self._handle_resource_mode,
                "ask_existing_vpc": self._handle_existing_vpc_choice,
                "ask_existing_subnet": self._handle_existing_subnet_choice,
                "ask_existing_sg": self._handle_existing_sg_choice,
                "ask_keypair_mode": self._handle_keypair_mode,
                "ask_keypair_name": self._handle_keypair_name,
                "awaiting_security_approval": self._handle_security_approval_response,
                "deploy_confirm": self._handle_deploy_confirm,
                "approval_request": self._handle_approval_response,
            }

            handler = handlers.get(step, self._handle_initial)
            return await handler(msg, user_email, user_info)

        except Exception as e:
            logger.exception("process_user_message error: %s", e)
            return {"message": f"Error: {e}", "buttons": [{"text": "Cancel", "action": "cancel"}], "show_text_input": True}

    async def _handle_initial(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.user_context[user_email]["config"]
        
        low_msg = self._normalize_input(message)
        if not any(word in low_msg for word in ["ec2", "instance", "server", "vm", "create", "deploy"]):
            return {"message": "I help you create cloud resources. What would you like to deploy?", "show_text_input": True}
        
        parsed = await self._parse_initial_request(message, user_info)
        inferred = parsed.get("inferred", {}) or {}
        
        for key in ("environment", "instance_type", "operating_system", "storage_size", "region"):
            if inferred.get(key) is not None:
                cfg[key] = inferred.get(key)

        env = cfg.get("environment")
        if env:
            if not check_environment_access(user_info, env):
                self.user_context[user_email]["step"] = "approval_request"
                self.user_context[user_email]["requested_environment"] = env
                return {
                    "message": f"No access to {env.upper()} environment. Request approval from {user_info.get('manager_email')}?",
                    "buttons": [{"text": "Yes", "action": "yes"}, {"text": "No", "action": "no"}],
                    "show_text_input": True
                }
        else:
            return await self._ask_environment(user_email, user_info)
        
        missing = self._get_missing_basic_fields(cfg)
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _parse_initial_request(self, message: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        if self.provider:
            try:
                return await self.provider.extract_requirements(message, {"user": user_info})
            except Exception as e:
                logger.warning(f"LLM parsing failed: {e}")
        
        return self._heuristic_fallback(message)

    def _heuristic_fallback(self, text: str) -> Dict[str, Any]:
        low = self._normalize_input(text) or ""
        
        env = None
        for e in ("dev", "qa", "prod"):
            if re.search(rf"\b{e}\b", low):
                env = e
                break

        it = None
        m = re.search(r"\b([tmcmr]?\d+(?:\.\w+)?)\b", low)
        if m:
            it = m.group(1)

        os_type = None
        for k in ("ubuntu22", "ubuntu", "amazon linux", "amazon-linux", "windows", "centos"):
            if k in low:
                os_type = k.replace(" ", "-")
                break

        region = None
        r = re.search(r"\b([a-z]{2}-[a-z]+-\d+)\b", low)
        if r:
            region = r.group(1)

        sz = None
        s = re.search(r"(\d+)\s?gb", low)
        if s:
            sz = int(s.group(1))

        inferred = {
            "environment": env,
            "instance_type": it,
            "operating_system": os_type,
            "storage_size": sz,
            "region": region,
        }

        return {"intent": "create_instance", "inferred": inferred, "missing": [], "confidence": 0.7}

    def _get_missing_basic_fields(self, cfg: Dict[str, Any]) -> List[str]:
        required = ["environment", "instance_type", "operating_system", "storage_size", "region"]
        missing = []
        for field in required:
            if not cfg.get(field):
                missing.append(field)
        return missing

    async def _ask_environment(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        envs = [e for e in ["dev", "qa", "prod"] if check_environment_access(user_info, e)]
        
        if not envs:
            ctx["step"] = "approval_request"
            ctx["requested_environment"] = "prod"
            return {
                "message": f"No environment access. Request approval from {user_info.get('manager_email')}?",
                "buttons": [{"text": "Yes", "action": "yes"}, {"text": "No", "action": "no"}],
                "show_text_input": True
            }
        
        ctx["step"] = "ask_environment"
        return {
            "message": f"Which environment? Available: {', '.join(envs)}",
            "buttons": [{"text": e.upper(), "action": e} for e in envs],
            "show_text_input": True
        }

    async def _ask_for_next_field(self, field: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        
        if field == "instance_type":
            ctx["step"] = "ask_instance_type"
            env = ctx["config"].get("environment", "dev")
            dept = user_info.get("department", "")
            allowed = get_department_limits("aws", env, dept).get("allowed_instance_types", ["t3.micro"])
            return {
                "message": f"Instance type? Allowed for {env.upper()}: {', '.join(allowed)}",
                "buttons": [{"text": t, "action": t} for t in allowed[:5]],
                "show_text_input": True
            }
        
        elif field == "operating_system":
            ctx["step"] = "ask_os"
            return {
                "message": "Operating System?",
                "buttons": [
                    {"text": "Ubuntu", "action": "ubuntu"},
                    {"text": "Amazon Linux", "action": "amazon-linux"},
                    {"text": "Windows", "action": "windows"},
                    {"text": "CentOS", "action": "centos"}
                ],
                "show_text_input": True
            }
        
        elif field == "storage_size":
            ctx["step"] = "ask_storage"
            default_storage = 8  # Set default here, not from .env
            return {
                "message": f"Storage size in GB? (Default: {default_storage})",
                "buttons": [
                    {"text": str(default_storage), "action": str(default_storage)}, 
                    {"text": "20", "action": "20"}, 
                    {"text": "50", "action": "50"}
                ],
                "show_text_input": True
            }
        
        elif field == "region":
            ctx["step"] = "ask_region"
            env = ctx["config"].get("environment", "dev")
            dept = user_info.get("department", "")
            allowed = get_department_limits("aws", env, dept).get("allowed_regions", ["us-east-1"])
            return {
                "message": f"AWS Region? Allowed for {env.upper()}: {', '.join(allowed)}",
                "buttons": [{"text": r, "action": r} for r in allowed[:4]],
                "show_text_input": True
            }
        
        else:
            return await self._ask_environment(user_email, user_info)

    async def _handle_environment_selection(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        env = self._normalize_env_input(message)
        if not env:
            return {"message": "Please choose dev, qa, or prod.", "show_text_input": True}
        
        if not check_environment_access(user_info, env):
            ctx = self.user_context[user_email]
            ctx["step"] = "approval_request"
            ctx["requested_environment"] = env
            return {
                "message": f"No access to {env.upper()}. Request approval from {user_info.get('manager_email')}?",
                "buttons": [{"text": "Yes", "action": "yes"}, {"text": "No", "action": "no"}],
                "show_text_input": True
            }
        
        self.user_context[user_email]["config"]["environment"] = env
        
        missing = self._get_missing_basic_fields(self.user_context[user_email]["config"])
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _handle_instance_type(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        itype = message.strip()
        ctx = self.user_context[user_email]
        env = ctx["config"].get("environment")
        dept = user_info.get("department", "")
        allowed = get_department_limits("aws", env, dept).get("allowed_instance_types", [])
        
        if allowed and itype not in allowed:
            return {
                "message": f"Instance type '{itype}' not allowed in {env.upper()}. Allowed: {', '.join(allowed)}",
                "buttons": [{"text": t, "action": t} for t in allowed[:5]],
                "show_text_input": True
            }
        
        ctx["config"]["instance_type"] = itype
        
        missing = self._get_missing_basic_fields(ctx["config"])
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _handle_operating_system(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        os_input = self._normalize_input(message)
        
        os_mapping = {
            "ubuntu": "ubuntu",
            "ubuntu22": "ubuntu22",
            "amazon-linux": "amazon-linux",
            "amazon linux": "amazon-linux",
            "windows": "windows",
            "centos": "centos"
        }
        
        os_type = os_mapping.get(os_input)
        if not os_type:
            return {
                "message": "Invalid OS. Please choose Ubuntu, Amazon Linux, Windows, or CentOS.",
                "buttons": [
                    {"text": "Ubuntu", "action": "ubuntu"},
                    {"text": "Amazon Linux", "action": "amazon-linux"},
                    {"text": "Windows", "action": "windows"}
                ],
                "show_text_input": True
            }
        
        self.user_context[user_email]["config"]["operating_system"] = os_type
        
        missing = self._get_missing_basic_fields(self.user_context[user_email]["config"])
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _handle_storage(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        digits = re.findall(r"\d+", message)
        if not digits:
            return {"message": "Please enter storage size in GB (e.g., 20, 50, 100)", "show_text_input": True}
        
        size = int(digits[0])
        ctx = self.user_context[user_email]
        env = ctx["config"].get("environment")
        dept = user_info.get("department", "")
        limits = get_department_limits("aws", env, dept)
        max_gb = limits.get("max_storage_gb", 100)
        
        if size > max_gb:
            return {
                "message": f"Storage {size}GB exceeds maximum {max_gb}GB for {env.upper()}. Choose smaller size:",
                "buttons": [{"text": str(max_gb), "action": str(max_gb)}],
                "show_text_input": True
            }
        
        ctx["config"]["storage_size"] = size
        
        missing = self._get_missing_basic_fields(ctx["config"])
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _handle_region(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        region = self._normalize_region_input(message)
        if not region:
            return {"message": "Please use valid AWS region format (e.g., us-east-1, us-west-2)", "show_text_input": True}
        
        ctx = self.user_context[user_email]
        env = ctx["config"].get("environment")
        dept = user_info.get("department", "")
        allowed = get_department_limits("aws", env, dept).get("allowed_regions", [])
        
        if allowed and region not in allowed:
            return {
                "message": f"Region {region} not allowed for {env.upper()}. Allowed: {', '.join(allowed)}",
                "buttons": [{"text": r, "action": r} for r in allowed],
                "show_text_input": True
            }
        
        ctx["config"]["region"] = region
        
        missing = self._get_missing_basic_fields(ctx["config"])
        if missing:
            return await self._ask_for_next_field(missing[0], user_email, user_info)
        
        return await self._begin_technical_approval(user_email, user_info)

    async def _begin_technical_approval(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        cfg = ctx["config"]
        
        validation_ok, validation_msg = self._validate_core_configuration(cfg, user_info)
        if not validation_ok:
            return {"message": validation_msg, "show_text_input": True}
        
        ctx["step"] = "awaiting_technical_approval"
        summary = self._format_technical_approval_summary(cfg)
        
        return {
            "message": f"Technical Approval Required:\n{summary}\n\nApprove this configuration?",
            "buttons": [{"text": "Yes", "action": "yes"}, {"text": "No", "action": "no"}],
            "show_text_input": True
        }

    def _validate_core_configuration(self, cfg: Dict[str, Any], user_info: Dict[str, Any]) -> tuple[bool, str]:
        env = cfg.get("environment")
        dept = user_info.get("department", "")
        limits = get_department_limits("aws", env, dept)
        
        allowed_types = limits.get("allowed_instance_types", [])
        if cfg.get("instance_type") and allowed_types and cfg.get("instance_type") not in allowed_types:
            return False, f"Instance {cfg.get('instance_type')} not allowed in {env}. Allowed: {', '.join(allowed_types)}"
        
        size = cfg.get("storage_size", 20)
        max_gb = limits.get("max_storage_gb", 100)
        if size > max_gb:
            return False, f"{size}GB exceeds max {max_gb}GB for {env}. Choose <= {max_gb}"
        
        region = cfg.get("region")
        if region:
            allowed_regions = limits.get("allowed_regions", [])
            if allowed_regions and region not in allowed_regions:
                return False, f"Region {region} not allowed for {env}. Choose: {', '.join(allowed_regions)}"
        
        return True, ""

    def _format_technical_approval_summary(self, cfg: Dict[str, Any]) -> str:
        return (f"Environment: {cfg.get('environment', '').upper()}\n"
                f"Instance Type: {cfg.get('instance_type')}\n"
                f"Operating System: {cfg.get('operating_system')}\n"
                f"Storage: {cfg.get('storage_size')}GB\n"
                f"Region: {cfg.get('region')}")

    async def _handle_technical_approval_response(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        response = self._normalize_input(message)
        
        if response in {"yes", "y", "approve", "approved"}:
            ctx = self.user_context[user_email]
            ctx["technical_approval"] = True
            
            ctx["step"] = "ask_resource_mode"
            ctx.setdefault("resource_order", ["vpc", "subnet", "security_group"])
            ctx.setdefault("resource_idx", 0)
            
            return {
                "message": "Technical configuration approved. Now configuring networking.\n\nVPC (Virtual Private Cloud) - use default or existing?",
                "buttons": [{"text": "Default", "action": "default"}, {"text": "Existing", "action": "existing"}],
                "show_text_input": True
            }
        
        elif response in {"no", "n", "deny", "denied"}:
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Request cancelled. Ready for new request.", "show_text_input": True}
        
        return {"message": "Please answer yes or no for technical approval.", "show_text_input": True}

    async def _handle_resource_mode(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        msg = self._normalize_input(message)
        ctx = self.user_context[user_email]
        order = ctx.get("resource_order", ["vpc", "subnet", "security_group"])
        idx = ctx.get("resource_idx", 0)
        
        if msg == "cancel":
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Cancelled. Ready for new request.", "buttons": [], "show_text_input": True}
        
        if msg == "default":
            resource = order[idx] if idx < len(order) else "unknown"
            ctx["config"][f"{resource}_mode"] = "default"
            return await self._move_to_next_resource(user_email, user_info)
        
        if idx >= len(order):
            return await self._configure_keypair(user_email, user_info)
        
        resource = order[idx]
        
        if msg not in {"default", "existing"}:
            return {
                "message": f"For {resource.upper()}, choose 'default' or 'existing'",
                "buttons": [{"text": "Default", "action": "default"}, {"text": "Existing", "action": "existing"}, {"text": "Cancel", "action": "cancel"}],
                "show_text_input": True
            }
        
        ctx["config"][f"{resource}_mode"] = msg
        
        if msg == "existing":
            return await self._fetch_and_select_existing_resource(resource, user_email, user_info)
        else:
            return await self._move_to_next_resource(user_email, user_info)

    async def _fetch_and_select_existing_resource(self, resource: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        region = ctx["config"].get("region")
        env = ctx["config"].get("environment")
        
        try:
            fetcher = AWSResourceFetcher(env, region)
            
            if not fetcher.credentials_ok:
                logger.warning(f"AWS credentials validation failed for region {region}")
                return {
                    "message": f"AWS credentials not configured for region {region}. Choose Default or Cancel:",
                    "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
            
            if resource == "vpc":
                logger.info(f"Fetching VPCs in region {region}")
                resources = await fetcher.get_vpcs()
                
                if not resources:
                    return {
                        "message": f"No existing VPCs found in region {region}. Choose Default or Cancel:",
                        "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                        "show_text_input": True
                    }
                
                ctx.setdefault("lists", {})["vpcs"] = resources
                ctx["step"] = "ask_existing_vpc"
                
                options_text = "\n".join([f"{i+1}. {v['id']} ({v['name']}) - {v['cidr']}" for i, v in enumerate(resources[:5])])
                return {
                    "message": f"Found {len(resources)} VPCs in {region}:\n{options_text}\n\nSelect VPC ID or choose Default:",
                    "buttons": [{"text": v["id"], "action": v["id"]} for v in resources[:5]] + [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
            
            elif resource == "subnet":
                vpc_id = None
                if ctx["config"].get("vpc_mode") == "existing":
                    vpc_id = ctx["config"].get("existing_vpc_id")
                
                logger.info(f"Fetching subnets in region {region}, VPC: {vpc_id or 'all'}")
                resources = await fetcher.get_subnets(vpc_id)
                
                if not resources:
                    vpc_context = f" in VPC {vpc_id}" if vpc_id else ""
                    return {
                        "message": f"No existing subnets found in region {region}{vpc_context}. Choose Default or Cancel:",
                        "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                        "show_text_input": True
                    }
                
                ctx.setdefault("lists", {})["subnets"] = resources
                ctx["step"] = "ask_existing_subnet"
                
                options_text = "\n".join([f"{i+1}. {s['id']} ({s['name']}) - AZ: {s['availability_zone']}, VPC: {s['vpc_id']}" for i, s in enumerate(resources[:5])])
                vpc_info = f" in VPC {vpc_id}" if vpc_id else ""
                return {
                    "message": f"Found {len(resources)} subnets{vpc_info}:\n{options_text}\n\nSelect Subnet ID or choose Default:",
                    "buttons": [{"text": s["id"], "action": s["id"]} for s in resources[:5]] + [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
            
            elif resource == "security_group":
                vpc_id = None
                if ctx["config"].get("vpc_mode") == "existing":
                    vpc_id = ctx["config"].get("existing_vpc_id")
                
                logger.info(f"Fetching security groups in region {region}, VPC: {vpc_id or 'all'}")
                resources = await fetcher.get_security_groups(vpc_id)
                
                if not resources:
                    vpc_context = f" in VPC {vpc_id}" if vpc_id else ""
                    return {
                        "message": f"No existing security groups found in region {region}{vpc_context}. Choose Default or Cancel:",
                        "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                        "show_text_input": True
                    }
                
                ctx.setdefault("lists", {})["security_groups"] = resources
                ctx["step"] = "ask_existing_sg"
                
                options_text = "\n".join([f"{i+1}. {sg['id']} ({sg['name']}) - {sg['description'][:50]}" for i, sg in enumerate(resources[:5])])
                vpc_info = f" in VPC {vpc_id}" if vpc_id else ""
                return {
                    "message": f"Found {len(resources)} security groups{vpc_info}:\n{options_text}\n\nSelect Security Group ID or choose Default:",
                    "buttons": [{"text": sg["id"], "action": sg["id"]} for sg in resources[:5]] + [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
                
        except Exception as e:
            logger.error(f"Exception while fetching {resource} resources in {region}: {e}")
            return {
                "message": f"Error fetching {resource} resources from AWS in region {region}: {str(e)}\nChoose Default or Cancel:",
                "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                "show_text_input": True
            }

    async def _move_to_next_resource(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        order = ctx.get("resource_order", ["vpc", "subnet", "security_group"])
        ctx["resource_idx"] = ctx.get("resource_idx", 0) + 1
        
        if ctx["resource_idx"] < len(order):
            next_resource = order[ctx["resource_idx"]]
            return {
                "message": f"{next_resource.upper()} - use default or existing?",
                "buttons": [{"text": "Default", "action": "default"}, {"text": "Existing", "action": "existing"}],
                "show_text_input": True
            }
        else:
            return await self._configure_keypair(user_email, user_info)

    async def _handle_existing_vpc_choice(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        msg = self._normalize_input(message)
        ctx = self.user_context[user_email]
        
        if msg == "default":
            ctx["config"]["vpc_mode"] = "default"
            return await self._move_to_next_resource(user_email, user_info)
        
        if msg == "cancel":
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Cancelled. Ready for new request.", "buttons": [], "show_text_input": True}
        
        vpc_id = message.strip()
        vpcs = ctx.get("lists", {}).get("vpcs", [])
        
        if vpcs:
            valid_vpc_ids = {v["id"] for v in vpcs}
            if vpc_id not in valid_vpc_ids:
                return {
                    "message": f"Invalid VPC ID '{vpc_id}'. Please select from the list:\n" + 
                              "\n".join([f"• {v['id']} ({v['name']})" for v in vpcs[:5]]),
                    "buttons": [{"text": v["id"], "action": v["id"]} for v in vpcs[:5]] + 
                              [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
        else:
            try:
                region = ctx["config"].get("region")
                env = ctx["config"].get("environment")
                fetcher = AWSResourceFetcher(env, region)
                if fetcher.credentials_ok:
                    vpc_info = await fetcher.get_vpc_by_id(vpc_id)
                    if not vpc_info:
                        return {
                            "message": f"VPC '{vpc_id}' not found in region {region}. Choose Default or Cancel:",
                            "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                            "show_text_input": True
                        }
                else:
                    logger.warning("Cannot validate VPC ID - credentials issue")
            except Exception as e:
                logger.warning(f"VPC validation failed: {e}")
        
        ctx["config"]["existing_vpc_id"] = vpc_id
        logger.info(f"Selected VPC: {vpc_id}")
        return await self._move_to_next_resource(user_email, user_info)

    async def _handle_existing_subnet_choice(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        msg = self._normalize_input(message)
        ctx = self.user_context[user_email]
        
        if msg == "default":
            ctx["config"]["subnet_mode"] = "default"
            return await self._move_to_next_resource(user_email, user_info)
        
        if msg == "cancel":
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Cancelled. Ready for new request.", "buttons": [], "show_text_input": True}
        
        subnet_id = message.strip()
        subnets = ctx.get("lists", {}).get("subnets", [])
        
        if subnets:
            valid_subnet_ids = {s["id"] for s in subnets}
            if subnet_id not in valid_subnet_ids:
                return {
                    "message": f"Invalid Subnet ID '{subnet_id}'. Please select from the list:\n" +
                              "\n".join([f"• {s['id']} ({s['name']}) - AZ: {s['availability_zone']}" for s in subnets[:5]]),
                    "buttons": [{"text": s["id"], "action": s["id"]} for s in subnets[:5]] + 
                              [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
            
            selected_subnet = next((s for s in subnets if s["id"] == subnet_id), None)
            if selected_subnet:
                subnet_vpc = selected_subnet.get("vpc_id")
                selected_vpc = ctx["config"].get("existing_vpc_id")
                
                if ctx["config"].get("vpc_mode") == "existing" and selected_vpc and subnet_vpc != selected_vpc:
                    return {
                        "message": f"Error: Subnet {subnet_id} belongs to VPC {subnet_vpc}, but you selected VPC {selected_vpc}.\nChoose subnet in the correct VPC:",
                        "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                        "show_text_input": True
                    }
        else:
            try:
                region = ctx["config"].get("region")
                env = ctx["config"].get("environment")
                fetcher = AWSResourceFetcher(env, region)
                if fetcher.credentials_ok:
                    subnet_info = await fetcher.get_subnet_by_id(subnet_id)
                    if not subnet_info:
                        return {
                            "message": f"Subnet '{subnet_id}' not found in region {region}. Choose Default or Cancel:",
                            "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                            "show_text_input": True
                        }
                    
                    subnet_vpc = subnet_info.get("vpc_id")
                    selected_vpc = ctx["config"].get("existing_vpc_id")
                    if ctx["config"].get("vpc_mode") == "existing" and selected_vpc and subnet_vpc != selected_vpc:
                        return {
                            "message": f"Error: Subnet {subnet_id} belongs to VPC {subnet_vpc}, not selected VPC {selected_vpc}.",
                            "buttons": [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                            "show_text_input": True
                        }
            except Exception as e:
                logger.warning(f"Subnet validation failed: {e}")
        
        ctx["config"]["existing_subnet_id"] = subnet_id
        logger.info(f"Selected Subnet: {subnet_id}")
        return await self._move_to_next_resource(user_email, user_info)

    async def _handle_existing_sg_choice(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        msg = self._normalize_input(message)
        ctx = self.user_context[user_email]
        
        if msg == "default":
            ctx["config"]["security_group_mode"] = "default"
            return await self._move_to_next_resource(user_email, user_info)
        
        if msg == "cancel":
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Cancelled. Ready for new request.", "buttons": [], "show_text_input": True}
        
        sg_id = message.strip()
        sgs = ctx.get("lists", {}).get("security_groups", [])
        
        if sgs:
            valid_sg_ids = {sg["id"] for sg in sgs}
            if sg_id not in valid_sg_ids:
                return {
                    "message": f"Invalid Security Group ID '{sg_id}'. Please select from the list:\n" +
                              "\n".join([f"• {sg['id']} ({sg['name']})" for sg in sgs[:5]]),
                    "buttons": [{"text": sg["id"], "action": sg["id"]} for sg in sgs[:5]] + 
                              [{"text": "Default", "action": "default"}, {"text": "Cancel", "action": "cancel"}],
                    "show_text_input": True
                }
        
        ctx["config"]["existing_sg_id"] = sg_id
        
        try:
            region = ctx["config"].get("region")
            env = ctx["config"].get("environment")
            fetcher = AWSResourceFetcher(env, region)
            
            if fetcher.credentials_ok:
                logger.info(f"Fetching security group rules for {sg_id}")
                rules = await fetcher.get_security_group_rules(sg_id)
                if rules:
                    ctx.setdefault("lists", {}).setdefault("sg_rules", {})[sg_id] = rules
                    logger.info(f"Successfully fetched rules for SG {sg_id}: {len(rules.get('ingress', []))} ingress, {len(rules.get('egress', []))} egress")
                else:
                    logger.warning(f"No rules found for security group {sg_id}")
            else:
                logger.warning("Cannot fetch SG rules - credential validation failed")
                
        except Exception as e:
            logger.error(f"Failed to fetch security group rules for {sg_id}: {e}")
        
        logger.info(f"Selected Security Group: {sg_id}")
        return await self._move_to_next_resource(user_email, user_info)

    async def _configure_keypair(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        ctx["step"] = "ask_keypair_mode"
        
        return {
            "message": "SSH Keypair setup:",
            "buttons": [
                {"text": "Use Existing", "action": "existing"},
                {"text": "Create New", "action": "new"},
                {"text": "Auto-generate", "action": "auto"}
            ],
            "show_text_input": True
        }

    async def _handle_keypair_mode(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        msg = self._normalize_input(message)
        ctx = self.user_context[user_email]
        
        # Handle different variations of auto-generate
        if msg in {"auto", "auto-generate", "autogenerate", "auto generate"}:
            msg = "auto"
        elif msg in {"existing", "use existing", "use-existing"}:
            msg = "existing"
        elif msg in {"new", "create new", "create-new"}:
            msg = "new"
        
        if msg not in {"existing", "new", "auto"}:
            return {
                "message": "Please choose 'existing', 'new', or 'auto' for keypair setup",
                "buttons": [
                    {"text": "Use Existing", "action": "existing"},
                    {"text": "Create New", "action": "new"},
                    {"text": "Auto-generate", "action": "auto"}
                ],
                "show_text_input": True
            }
        
        if msg == "existing":
            ctx["step"] = "ask_keypair_name"
            ctx["config"]["key_pair"] = {"type": "existing", "name": None}
            return {
                "message": "Enter the name of existing keypair:",
                "show_text_input": True
            }
        
        elif msg == "new":
            ctx["step"] = "ask_keypair_name"
            ctx["config"]["key_pair"] = {"type": "new", "name": None}
            return {
                "message": "Enter name for new keypair (or type 'auto' to auto-generate):",
                "show_text_input": True
            }
        
        elif msg == "auto":
            auto_name = f"auto-{user_info.get('department', 'user')}-{uuid.uuid4().hex[:6]}"
            ctx["config"]["key_pair"] = {"type": "new", "name": auto_name}
            return await self._begin_security_approval(user_email, user_info)

    async def _handle_keypair_name(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        name = message.strip()
        ctx = self.user_context[user_email]
        
        if not name:
            return {"message": "Please provide a keypair name or type 'auto'", "show_text_input": True}
        
        if name.lower() == "auto":
            auto_name = f"auto-{user_info.get('department', 'user')}-{uuid.uuid4().hex[:6]}"
            ctx["config"]["key_pair"]["name"] = auto_name
        else:
            ctx["config"]["key_pair"]["name"] = name
        
        return await self._begin_security_approval(user_email, user_info)

    async def _begin_security_approval(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        
        sg_info = self._format_security_group_info(ctx)
        
        ctx["step"] = "awaiting_security_approval"
        
        return {
            "message": f"Security Approval Required:\n\n{sg_info}\n\nApprove this security configuration?",
            "buttons": [{"text": "Yes", "action": "yes"}, {"text": "No", "action": "no"}],
            "show_text_input": True
        }

    def _format_security_group_info(self, ctx: Dict[str, Any]) -> str:
        cfg = ctx["config"]
        sg_mode = cfg.get("security_group_mode", "default")
        
        if sg_mode == "default":
            rules_text = "DEFAULT Security Group Rules:\n\n"
            rules_text += "INBOUND (Ingress):\n"
            for rule in DEFAULT_SG_RULES["ingress"]:
                port_range = f"Port {rule['from_port']}" if rule['from_port'] == rule['to_port'] else f"Ports {rule['from_port']}-{rule['to_port']}"
                rules_text += f"  ✓ {rule['description']}: {rule['protocol'].upper()} {port_range} from {', '.join(rule['ranges'])}\n"
            
            rules_text += "\nOUTBOUND (Egress):\n"
            for rule in DEFAULT_SG_RULES["egress"]:
                if rule['protocol'] == '-1':
                    rules_text += f"  ✓ {rule['description']}: All protocols/ports to {', '.join(rule['ranges'])}\n"
                else:
                    port_range = f"Port {rule['from_port']}" if rule['from_port'] == rule['to_port'] else f"Ports {rule['from_port']}-{rule['to_port']}"
                    rules_text += f"  ✓ {rule['description']}: {rule['protocol'].upper()} {port_range} to {', '.join(rule['ranges'])}\n"
        
        else:
            sg_id = cfg.get("existing_sg_id")
            rules = ctx.get("lists", {}).get("sg_rules", {}).get(sg_id)
            
            if rules and (rules.get("ingress") or rules.get("egress")):
                rules_text = f"EXISTING Security Group ({sg_id}) Rules:\n\n"
                
                rules_text += "INBOUND (Ingress):\n"
                ingress_rules = rules.get("ingress", [])
                if ingress_rules:
                    for i, rule in enumerate(ingress_rules, 1):
                        protocol = rule.get('protocol', 'unknown').upper()
                        if rule.get('from_port') == -1 or rule.get('protocol') == '-1':
                            port_info = "All ports"
                        elif rule.get('from_port') == rule.get('to_port'):
                            port_info = f"Port {rule.get('from_port')}"
                        else:
                            port_info = f"Ports {rule.get('from_port')}-{rule.get('to_port')}"
                        
                        ranges = rule.get('ranges', [])
                        sources = ', '.join(ranges) if ranges else 'No sources'
                        rules_text += f"  {i}. {protocol} {port_info} from {sources}\n"
                else:
                    rules_text += "  No inbound rules\n"
                
                rules_text += "\nOUTBOUND (Egress):\n"
                egress_rules = rules.get("egress", [])
                if egress_rules:
                    for i, rule in enumerate(egress_rules, 1):
                        protocol = rule.get('protocol', 'unknown').upper()
                        if rule.get('from_port') == -1 or rule.get('protocol') == '-1':
                            port_info = "All ports"
                        elif rule.get('from_port') == rule.get('to_port'):
                            port_info = f"Port {rule.get('from_port')}"
                        else:
                            port_info = f"Ports {rule.get('from_port')}-{rule.get('to_port')}"
                        
                        ranges = rule.get('ranges', [])
                        destinations = ', '.join(ranges) if ranges else 'No destinations'
                        rules_text += f"  {i}. {protocol} {port_info} to {destinations}\n"
                else:
                    rules_text += "  No outbound rules\n"
            
            else:
                rules_text = f"EXISTING Security Group ({sg_id}):\n\n"
                rules_text += "⚠️  Unable to fetch detailed security rules.\n"
                rules_text += "This could be due to:\n"
                rules_text += "  • Insufficient AWS permissions\n"
                rules_text += "  • Network connectivity issues\n"
                rules_text += "  • Security group doesn't exist\n\n"
                rules_text += "Please verify the security group manually or choose default security group for standard web/SSH access."
        
        return rules_text

    async def _handle_security_approval_response(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        response = self._normalize_input(message)
        
        if response in {"yes", "y", "approve", "approved"}:
            ctx = self.user_context[user_email]
            ctx["security_approval"] = True
            return await self._final_deployment_confirmation(user_email, user_info)
        
        elif response in {"no", "n", "deny", "denied"}:
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Security configuration rejected. Request cancelled.", "show_text_input": True}
        
        return {"message": "Please answer yes or no for security approval.", "show_text_input": True}

    async def _final_deployment_confirmation(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        cfg = ctx["config"]
        
        if not ctx.get("technical_approval") or not ctx.get("security_approval"):
            return {"message": "Both technical and security approvals required before deployment.", "show_text_input": True}
        
        summary = self._generate_deployment_summary(cfg)
        
        ctx["step"] = "deploy_confirm"
        
        return {
            "message": f"Ready for Deployment:\n\n{summary}\n\nDeploy this configuration?",
            "buttons": [{"text": "Deploy", "action": "deploy"}, {"text": "Cancel", "action": "cancel"}],
            "show_text_input": True
        }

    def _generate_deployment_summary(self, cfg: Dict[str, Any]) -> str:
        keypair_desc = f"{cfg.get('key_pair', {}).get('type', 'unknown')} keypair"
        if cfg.get('key_pair', {}).get('name'):
            keypair_desc += f": {cfg['key_pair']['name']}"
        
        vpc_desc = cfg.get("vpc_mode", "default")
        if cfg.get("existing_vpc_id"):
            vpc_desc += f": {cfg['existing_vpc_id']}"
        
        subnet_desc = cfg.get("subnet_mode", "default")
        if cfg.get("existing_subnet_id"):
            subnet_desc += f": {cfg['existing_subnet_id']}"
        
        sg_desc = cfg.get("security_group_mode", "default")
        if cfg.get("existing_sg_id"):
            sg_desc += f": {cfg['existing_sg_id']}"
        
        summary = (
            f"Environment: {cfg.get('environment', '').upper()}\n"
            f"Instance Type: {cfg.get('instance_type')}\n"
            f"Operating System: {cfg.get('operating_system')}\n"
            f"Storage: {cfg.get('storage_size')}GB\n"
            f"Region: {cfg.get('region')}\n"
            f"VPC: {vpc_desc}\n"
            f"Subnet: {subnet_desc}\n"
            f"Security Group: {sg_desc}\n"
            f"Keypair: {keypair_desc}"
        )
        
        return summary

    async def _handle_deploy_confirm(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        response = self._normalize_input(message)
        
        if response in {"deploy", "yes", "y"}:
            return await self._execute_deployment(user_email, user_info)
        else:
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Deployment cancelled. Ready for new request.", "buttons": [], "show_text_input": True}

    async def _execute_deployment(self, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.user_context[user_email]
        cfg = ctx["config"]
        
        try:
            from .infrastructure import create_infrastructure_request
        except Exception as e:
            logger.exception("Failed to import create_infrastructure_request: %s", e)
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Internal error: deployment service unavailable.", "buttons": [], "show_text_input": True}
        
        req_id = f"{user_info.get('department', 'unknown').lower()}_aws_{cfg['environment']}_{uuid.uuid4().hex[:8]}"
        
        payload = {
            "user_id": user_info.get("user_id"),
            "user_email": user_info.get("email"),
            "request_identifier": req_id,
            "cloud_provider": "aws",
            "environment": cfg["environment"],
            "resource_type": "ec2",
            "parameters": {
                "instance_type": cfg.get("instance_type"),
                "region": cfg.get("region"),
                "operating_system": cfg.get("operating_system"),
                "storage_size": cfg.get("storage_size"),
                "key_pair": cfg.get("key_pair", {"type": "new", "name": None}),
                "vpc": {"mode": cfg.get("vpc_mode", "default"), "id": cfg.get("existing_vpc_id", "")},
                "subnet": {"mode": cfg.get("subnet_mode", "default"), "id": cfg.get("existing_subnet_id", "")},
                "security_group": {"mode": cfg.get("security_group_mode", "default"), "id": cfg.get("existing_sg_id", "")}
            }
        }
        
        try:
            created_id = await create_infrastructure_request(payload)
            logger.info("Infrastructure request created: %s (returned %s)", req_id, created_id)
            
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            
            return {
                "message": f"Deployment initiated successfully!\n\nRequest ID: {req_id.split('_')[-1]}\n\nYour EC2 instance is being provisioned. You'll receive notifications when it's ready.",
                "buttons": [],
                "show_text_input": True
            }
            
        except Exception as e:
            logger.exception("Deployment execution failed: %s", e)
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {
                "message": f"Deployment failed: {str(e)}\n\nPlease try again or contact support.",
                "buttons": [],
                "show_text_input": True
            }

    async def _handle_approval_response(self, message: str, user_email: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        response = self._normalize_input(message)
        
        if response in {"yes", "y"}:
            env = self.user_context[user_email].get("requested_environment", "dev")
            try:
                from .email_service import send_environment_approval_email
                approval_id = f"approval_{uuid.uuid4().hex[:8]}"
                await send_environment_approval_email(
                    user_info.get('manager_email'),
                    user_info.get('name'),
                    env,
                    approval_id
                )
                self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
                return {
                    "message": f"Approval request sent to {user_info.get('manager_email')} for {env.upper()} environment access.\n\nYou'll receive notification when decided.",
                    "buttons": [],
                    "show_text_input": True
                }
            except Exception as e:
                logger.exception("Failed to send approval email")
                return {"message": f"Failed to send approval email: {str(e)}", "show_text_input": True}
        
        elif response in {"no", "n"}:
            self.user_context[user_email] = {"step": "initial", "config": {}, "lists": {}}
            return {"message": "Environment approval request cancelled. Ready for new request.", "show_text_input": True}
        
        return {"message": "Please answer yes or no for sending approval request.", "show_text_input": True}