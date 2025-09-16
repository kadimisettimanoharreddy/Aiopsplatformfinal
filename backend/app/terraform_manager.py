import os
import errno
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import asyncio

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REPO_ROOT_ENV = "REPO_ROOT"

def find_repo_root(start: Optional[Path] = None, max_up: int = 8) -> Optional[Path]:
    env_root = os.getenv(REPO_ROOT_ENV)
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            logger.info("find_repo_root: using REPO_ROOT env -> %s", p)
            return p

    p = (start or Path.cwd()).resolve()
    for _ in range(max_up + 1):
        if (p / "terraform").exists() or (p / ".git").exists():
            logger.info("find_repo_root: detected repo root at %s", p)
            return p
        if p.parent == p:
            break
        p = p.parent
    logger.warning("find_repo_root: repo root not found from %s", start or Path.cwd())
    return None

def _ensure_dir(path: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def _get_user_info(user: Optional[Any], request_obj: Optional[Any] = None) -> Dict[str, str]:
    """Extract user information with proper fallbacks"""
    user_info = {
        "department": "unknown",
        "email": "system@aiops-platform.com",
        "name": "system"
    }
    
    # Try to get from user object first
    if user:
        user_info["department"] = getattr(user, "department", "unknown")
        user_info["email"] = getattr(user, "email", "system@aiops-platform.com")
        user_info["name"] = getattr(user, "name", "system")
    
    # Try to get from request object if user is None
    elif request_obj:
        # If request_obj has user_email or created_by fields
        if hasattr(request_obj, 'user_email') and request_obj.user_email:
            user_info["email"] = request_obj.user_email
        elif hasattr(request_obj, 'created_by') and request_obj.created_by:
            user_info["email"] = request_obj.created_by
            
        # Extract name from email if available
        if user_info["email"] != "system@aiops-platform.com":
            user_info["name"] = user_info["email"].split("@")[0].replace(".", "-")
    
    # Ensure department is never empty
    if not user_info["department"] or user_info["department"].strip() == "":
        user_info["department"] = "unknown"
    
    # Ensure email is never empty
    if not user_info["email"] or user_info["email"].strip() == "":
        user_info["email"] = "system@aiops-platform.com"
    
    # Ensure name is never empty
    if not user_info["name"] or user_info["name"].strip() == "":
        user_info["name"] = "system"
    
    return user_info

def _parse_keypair_config(params: Dict[str, Any], user_info: Dict[str, str], request_identifier: str) -> Dict[str, Any]:
    """
    Enhanced keypair parsing to handle different frontend formats and configurations.
    """
    keypair_config = {
        "key_name": "default",
        "create_new_keypair": False
    }
    
    # Check various possible parameter names for keypair configuration
    key_pair = (
        params.get("key_pair") or 
        params.get("keypair") or 
        params.get("keyPair") or
        params.get("ssh_key") or
        {}
    )
    
    logger.info(f"Raw keypair config from params: {key_pair}")
    
    # Handle different data types and structures
    if isinstance(key_pair, dict):
        # Check for "new" keypair creation
        keypair_type = key_pair.get("type", "").lower()
        keypair_mode = key_pair.get("mode", "").lower()
        
        # Multiple ways frontend might indicate "new" keypair
        is_new_keypair = (
            keypair_type == "new" or
            keypair_mode == "new" or 
            key_pair.get("createNew", False) or
            key_pair.get("create_new", False) or
            key_pair.get("auto_generate", False)
        )
        
        if is_new_keypair:
            # Extract custom name or generate one
            custom_name = (
                key_pair.get("name") or 
                key_pair.get("keyName") or 
                key_pair.get("keypair_name")
            )
            
            if custom_name and custom_name.strip():
                keypair_config["key_name"] = custom_name.strip()
            else:
                # Auto-generate keypair name
                dept_clean = user_info["department"].lower().replace(" ", "-").replace("_", "-")
                req_suffix = request_identifier.split('_')[-1] if '_' in request_identifier else request_identifier[-8:]
                keypair_config["key_name"] = f"auto-{dept_clean}-{req_suffix}"
            
            keypair_config["create_new_keypair"] = True
            logger.info(f"New keypair will be created: {keypair_config['key_name']}")
            
        elif key_pair.get("name") or key_pair.get("keyName"):
            # Existing keypair specified
            keypair_config["key_name"] = key_pair.get("name") or key_pair.get("keyName")
            keypair_config["create_new_keypair"] = False
            logger.info(f"Using existing keypair: {keypair_config['key_name']}")
            
    elif isinstance(key_pair, str) and key_pair.strip():
        # Simple string format
        if key_pair.lower() in ["new", "auto", "generate"]:
            # Auto-generate new keypair
            dept_clean = user_info["department"].lower().replace(" ", "-").replace("_", "-")
            req_suffix = request_identifier.split('_')[-1] if '_' in request_identifier else request_identifier[-8:]
            keypair_config["key_name"] = f"auto-{dept_clean}-{req_suffix}"
            keypair_config["create_new_keypair"] = True
        else:
            # Use specified existing keypair
            keypair_config["key_name"] = key_pair.strip()
            keypair_config["create_new_keypair"] = False
    
    # Check alternative parameter names for backwards compatibility
    if not keypair_config["create_new_keypair"]:
        direct_key_name = params.get("key_name") or params.get("keyName")
        if direct_key_name and direct_key_name.strip():
            keypair_config["key_name"] = direct_key_name.strip()
    
    logger.info(f"Final keypair config: {keypair_config}")
    return keypair_config

def _render_tfvars_content(request_identifier: str, user: Optional[Any], params: Dict[str, Any], request_obj: Optional[Any] = None) -> str:
    default_storage = 8
    
    # Get user information with proper fallbacks
    user_info = _get_user_info(user, request_obj)
    
    tfvars = {
        "request_id": request_identifier,
        "department": user_info["department"],
        "created_by": user_info["email"],
        "environment": (params.get("environment") or params.get("env") or "dev"),
        "instance_type": params.get("instance_type", "t3.micro"),
        "storage_size": params.get("storage_size", default_storage),
        "region": params.get("region", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        "associate_public_ip": params.get("associate_public_ip", True),
    }

    os_map = {
        "ubuntu": ("ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*", ["099720109477"]),
        "ubuntu22": ("ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*", ["099720109477"]),
        "amazon-linux": ("amzn2-ami-hvm-*-x86_64-gp2", ["137112412989"]),
        "windows": ("Windows_Server-2019-English-Full-Base-*", ["137112412989"]),
        "centos": ("CentOS-8-*-x86_64-*", ["137112412989"])
    }
    os_type = (params.get("operating_system") or params.get("os") or "ubuntu").lower()
    ami_filter, ami_owners = os_map.get(os_type, os_map["ubuntu"])
    tfvars["ami_filter"] = ami_filter
    tfvars["ami_owners"] = ami_owners

    # Enhanced keypair handling with better parsing
    keypair_config = _parse_keypair_config(params, user_info, request_identifier)
    tfvars["key_name"] = keypair_config["key_name"]
    tfvars["create_new_keypair"] = keypair_config["create_new_keypair"]

    # Enhanced VPC handling
    vpc = params.get("vpc") or {}
    if vpc.get("mode") == "existing" and vpc.get("id"):
        tfvars["vpc_id"] = vpc.get("id")
        tfvars["use_existing_vpc"] = True
    else:
        tfvars["vpc_id"] = ""
        tfvars["use_existing_vpc"] = False

    # Enhanced Subnet handling
    subnet = params.get("subnet") or {}
    if subnet.get("mode") == "existing" and subnet.get("id"):
        tfvars["subnet_id"] = subnet.get("id")
        tfvars["use_existing_subnet"] = True
    else:
        tfvars["subnet_id"] = ""
        tfvars["use_existing_subnet"] = False

    # Enhanced Security Group handling
    security_group = params.get("security_group") or {}
    if security_group.get("mode") == "existing" and security_group.get("id"):
        tfvars["security_group_id"] = security_group.get("id")
        tfvars["use_existing_sg"] = True
    else:
        tfvars["security_group_id"] = ""
        tfvars["use_existing_sg"] = False

    # Instance tags with proper user info
    name_clean = user_info["name"].replace(" ", "-").replace(".", "-").lower()
    instance_tags = {
        "Name": f"{name_clean}-ec2-{request_identifier.split('_')[-1]}",
        "Department": user_info["department"],
        "Environment": tfvars.get("environment", "dev"),
        "RequestID": request_identifier,
        "CreatedBy": user_info["email"],
        "ManagedBy": "AIOps-Platform"
    }
    tfvars["instance_tags"] = instance_tags

    # Build HCL-like tfvars lines
    lines = []
    for k, v in tfvars.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f'{k} = {str(v).lower()}')
        elif isinstance(v, (int, float)):
            lines.append(f'{k} = {v}')
        elif isinstance(v, list):
            items = ', '.join([f'"{i}"' for i in v])
            lines.append(f'{k} = [{items}]')
        elif isinstance(v, dict):
            dict_items = []
            for kk, vv in v.items():
                dict_items.append(f'  "{kk}" = "{vv}"')
            lines.append(f'{k} = {{\n' + '\n'.join(dict_items) + '\n}}')
    
    logger.info(f"Generated tfvars for user: {user_info['email']}, department: {user_info['department']}, keypair: {tfvars['key_name']} (new: {tfvars['create_new_keypair']})")
    return '\n'.join(lines) + '\n'

class TerraformManager:
    async def generate_tfvars_for_request(
        self,
        request_identifier: str,
        params: Dict[str, Any] = None,
        user: Optional[Any] = None,
        request_obj: Optional[Any] = None,
        repo_root_override: Optional[str] = None,
    ) -> Tuple[Path, Optional[Path]]:
        params = params or (getattr(request_obj, "request_parameters", {}) if request_obj else {})
        if repo_root_override:
            repo_root = Path(repo_root_override).expanduser().resolve()
        else:
            repo_root = find_repo_root() or Path.cwd().resolve()

        logger.info("TerraformManager: using repo_root=%s", repo_root)

        cloud = (params.get("cloud") or params.get("cloud_provider") or getattr(request_obj, "cloud_provider", "aws")).lower()
        environment = (params.get("environment") or getattr(request_obj, "environment", None) or "dev").lower()

        requests_dir = repo_root / "terraform" / "environments" / cloud / environment / "requests"
        _ensure_dir(requests_dir)

        tfvars_path = requests_dir / f"{request_identifier}.tfvars"
        content = _render_tfvars_content(request_identifier, user, params, request_obj)

        tmp = tfvars_path.with_suffix(".tfvars.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(tfvars_path)

        logger.info("TerraformManager: generated tfvars file: %s", tfvars_path)

        clone_expected = Path("terraform") / "environments" / cloud / environment / "requests" / f"{request_identifier}.tfvars"
        return tfvars_path, clone_expected

def generate_tfvars_for_request_sync(request_identifier: str, params: Dict[str, Any] = None, user: Optional[Any] = None, request_obj: Optional[Any] = None, repo_root_override: Optional[str] = None):
    return asyncio.get_event_loop().run_until_complete(
        TerraformManager().generate_tfvars_for_request(request_identifier, params, user, request_obj, repo_root_override)
    )