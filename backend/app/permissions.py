# backend/app/permissions.py

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

PERMISSIONS_MATRIX: Dict[str, Dict[str, Dict[str, Any]]] = {
    "aws": {
        "dev": {
            "Engineering": {
                "allowed_instance_types": ["t3.micro", "t3.small", "t3.medium", "t3.large"],
                "allowed_regions": ["us-east-1", "us-west-2", "ap-south-1"],
                "max_storage_gb": 50,
                "requires_approval": False
            },
            "DataScience": {
                "allowed_instance_types": ["t3.medium", "t3.large", "t3.xlarge"],
                "allowed_regions": ["us-east-1", "ap-south-1"],
                "max_storage_gb": 100,
                "requires_approval": False
            },
            "DevOps": {
                "allowed_instance_types": ["t3.micro", "t3.small", "t3.medium", "t3.large", "m5.large"],
                "allowed_regions": ["us-east-1", "us-west-2", "ap-south-1", "eu-west-1"],
                "max_storage_gb": 100,
                "requires_approval": False
            },
            "Finance": {
                "allowed_instance_types": ["t3.micro"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 50,
                "requires_approval": True
            },
            "Marketing": {
                "allowed_instance_types": ["t3.micro", "t3.small"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 100,
                "requires_approval": True
            },
            "HR": {
                "allowed_instance_types": ["t3.micro"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 30,
                "requires_approval": True
            }
        },
        "qa": {
            "Engineering": {
                "allowed_instance_types": ["t3.small", "t3.medium"],
                "allowed_regions": ["us-east-1", "ap-south-1"],
                "max_storage_gb": 50,
                "requires_approval": True
            },
            "DataScience": {
                "allowed_instance_types": ["t3.large", "t3.xlarge"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 100,
                "requires_approval": True
            },
            "DevOps": {
                "allowed_instance_types": ["t3.small", "t3.medium", "t3.large"],
                "allowed_regions": ["us-east-1", "ap-south-1"],
                "max_storage_gb": 100,
                "requires_approval": True
            },
            "Finance": {
                "allowed_instance_types": ["t3.micro"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 30,
                "requires_approval": True
            },
            "Marketing": {
                "allowed_instance_types": ["t3.micro"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 50,
                "requires_approval": True
            },
            "HR": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            }
        },
        "prod": {
            "Engineering": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            },
            "DataScience": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            },
            "DevOps": {
                "allowed_instance_types": ["t3.medium", "t3.large", "m5.large"],
                "allowed_regions": ["us-east-1"],
                "max_storage_gb": 100,
                "requires_approval": True
            },
            "Finance": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            },
            "Marketing": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            },
            "HR": {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            }
        }
    }
}

def get_department_limits(cloud_provider: str, environment: str, department: str) -> Dict[str, Any]:
    try:
        cloud_provider = (cloud_provider or "aws").lower().strip()
        environment = (environment or "dev").lower().strip()
        department = (department or "").strip()
        
        if not department:
            return {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            }
        
        cloud_limits = PERMISSIONS_MATRIX.get(cloud_provider, {})
        env_limits = cloud_limits.get(environment, {})
        dept_limits = env_limits.get(department, {})
        
        if not dept_limits:
            return {
                "allowed_instance_types": [],
                "allowed_regions": [],
                "max_storage_gb": 0,
                "requires_approval": True
            }
        
        return dept_limits
        
    except Exception as e:
        logger.error(f"Error getting department limits: {e}")
        return {
            "allowed_instance_types": [],
            "allowed_regions": [],
            "max_storage_gb": 0,
            "requires_approval": True
        }

def check_environment_access(user_info: Dict[str, Any], environment: str) -> bool:
    try:
        if not environment:
            return False
            
        environment = environment.lower().strip()
        
        env_access = user_info.get("environment_access", {})
        if isinstance(env_access, dict) and environment in env_access:
            return bool(env_access[environment])
        
        department = user_info.get("department", "").strip()
        if not department:
            return False
        
        limits = get_department_limits("aws", environment, department)
        requires_approval = limits.get("requires_approval", True)
        
        if environment in ("dev", "qa") and not requires_approval:
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking environment access: {e}")
        return False

def can_create_resource(user_info: Dict[str, Any], params: Dict[str, Any]) -> bool:
    try:
        if not isinstance(params, dict):
            return False
        
        cloud = params.get("cloud_provider", "aws")
        environment = params.get("environment")
        instance_type = params.get("instance_type")
        region = params.get("region") 
        storage_size = params.get("storage_size")
        
        if not environment:
            return False
        
        if not check_environment_access(user_info, environment):
            return False
        
        department = user_info.get("department", "")
        limits = get_department_limits(cloud, environment, department)
        
        if instance_type:
            allowed_types = limits.get("allowed_instance_types", [])
            if allowed_types and instance_type not in allowed_types:
                return False
        
        if region:
            allowed_regions = limits.get("allowed_regions", [])
            if allowed_regions and region not in allowed_regions:
                return False
        
        if storage_size is not None:
            max_storage = limits.get("max_storage_gb")
            if max_storage is not None and storage_size > max_storage:
                return False
        
        if limits.get("requires_approval", False) and environment == "prod":
            env_access = user_info.get("environment_access", {})
            if not env_access.get("prod", False):
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error in can_create_resource: {e}")
        return False