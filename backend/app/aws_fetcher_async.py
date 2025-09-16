import asyncio
import logging
import os
from typing import List, Dict, Optional, Any
import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    EndpointConnectionError,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AWSResourceFetcher:
    def __init__(self, environment: Optional[str], region: Optional[str]):
        self.environment = (environment or "dev").lower().strip()
        self.region = (
            region
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        ).strip()

        # ⚠️ Temporary credentials for testing — REMOVE in production
        test_access_key = "AKIAW3MEBAXMUCVE2O"
        test_secret_key = "EBEn0VXUL93i6h5pDsBuc4I65lm/wUXzouItTjGwfm"

        self._session = boto3.session.Session(
            aws_access_key_id=test_access_key or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=test_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=self.region,
        )

        self.credentials_ok = False
        try:
            self._validate_credentials()
        except Exception as e:
            logger.info("AWS credentials validation failed or unavailable: %s", e)
            self.credentials_ok = False

    def _validate_credentials(self):
        sts = self._session.client("sts")
        response = sts.get_caller_identity()
        logger.info(
            "AWS credentials validated for region %s, Account: %s",
            self.region,
            response.get("Account", "Unknown"),
        )
        self.credentials_ok = True

    async def _run_in_thread(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _safe_call(self, label: str, fn):
        try:
            return await self._run_in_thread(fn)
        except (NoCredentialsError, EndpointConnectionError) as e:
            logger.error("%s fetch failed: %s", label, e)
            return []
        except ClientError as e:
            logger.error("%s client error: %s", label, e)
            return []
        except BotoCoreError as e:
            logger.error("%s core error: %s", label, e)
            return []
        except Exception as e:
            logger.exception("%s unexpected error: %s", label, e)
            return []

    async def get_key_pairs(self) -> List[str]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_key_pairs()
            return [kp.get("KeyName", "") for kp in r.get("KeyPairs", []) if kp.get("KeyName")]

        return await self._safe_call("KeyPairs", _fn)

    async def get_vpcs(self) -> List[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_vpcs()
            out = []
            for v in r.get("Vpcs", []):
                name = next((t["Value"] for t in (v.get("Tags") or []) if t.get("Key") == "Name"), "No Name")
                out.append({
                    "id": v.get("VpcId", ""),
                    "name": name,
                    "cidr": v.get("CidrBlock", ""),
                    "is_default": v.get("IsDefault", False),
                })
            return out

        return await self._safe_call("VPCs", _fn)

    async def get_subnets(self, vpc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            flt = [{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else []
            r = ec2.describe_subnets(Filters=flt) if flt else ec2.describe_subnets()
            out = []
            for s in r.get("Subnets", []):
                name = next((t["Value"] for t in (s.get("Tags") or []) if t.get("Key") == "Name"), "No Name")
                out.append({
                    "id": s.get("SubnetId", ""),
                    "name": name,
                    "cidr": s.get("CidrBlock", ""),
                    "vpc_id": s.get("VpcId", ""),
                    "availability_zone": s.get("AvailabilityZone", ""),
                    "public": s.get("MapPublicIpOnLaunch", False),
                })
            return out

        return await self._safe_call("Subnets", _fn)

    async def get_security_groups(self, vpc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            flt = [{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else []
            r = ec2.describe_security_groups(Filters=flt) if flt else ec2.describe_security_groups()
            out = []
            for g in r.get("SecurityGroups", []):
                out.append({
                    "id": g.get("GroupId", ""),
                    "name": g.get("GroupName", ""),
                    "description": g.get("Description", ""),
                    "vpc_id": g.get("VpcId", ""),
                    "raw": g,
                })
            return out

        return await self._safe_call("SecurityGroups", _fn)

    async def get_availability_zones(self) -> List[str]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_availability_zones()
            return [z.get("ZoneName") for z in r.get("AvailabilityZones", [])]

        return await self._safe_call("AvailabilityZones", _fn)

    async def get_vpc_by_id(self, vpc_id: str) -> Optional[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_vpcs(VpcIds=[vpc_id])
            vs = r.get("Vpcs", [])
            if not vs:
                return None
            v = vs[0]
            name = next((t["Value"] for t in (v.get("Tags") or []) if t.get("Key") == "Name"), "No Name")
            return {"id": v.get("VpcId", ""), "name": name, "cidr": v.get("CidrBlock", ""), "is_default": v.get("IsDefault", False)}

        return await self._safe_call("GetVPCById", _fn)

    async def get_subnet_by_id(self, subnet_id: str) -> Optional[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_subnets(SubnetIds=[subnet_id])
            subs = r.get("Subnets", [])
            if not subs:
                return None
            s = subs[0]
            name = next((t["Value"] for t in (s.get("Tags") or []) if t.get("Key") == "Name"), "No Name")
            return {"id": s.get("SubnetId", ""), "name": name, "cidr": s.get("CidrBlock", ""), "vpc_id": s.get("VpcId", "")}

        return await self._safe_call("GetSubnetById", _fn)

    async def get_security_group_rules(self, sg_id: str) -> Optional[Dict[str, Any]]:
        def _fn():
            ec2 = self._session.client("ec2")
            r = ec2.describe_security_groups(GroupIds=[sg_id])
            gs = r.get("SecurityGroups", [])
            if not gs:
                return None
            g = gs[0]

            def norm(rules):
                out = []
                for p in rules:
                    ranges = (
                        [x.get("CidrIp") for x in p.get("IpRanges", []) if x.get("CidrIp")]
                        + [x.get("CidrIpv6") for x in p.get("Ipv6Ranges", []) if x.get("CidrIpv6")]
                    )
                    out.append({
                        "protocol": p.get("IpProtocol"),
                        "from_port": p.get("FromPort"),
                        "to_port": p.get("ToPort"),
                        "ranges": ranges,
                    })
                return out

            return {"ingress": norm(g.get("IpPermissions", [])), "egress": norm(g.get("IpPermissionsEgress", []))}

        return await self._safe_call("GetSGRules", _fn)
