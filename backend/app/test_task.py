# test_task.py
import asyncio
import sys
import os
import uuid

sys.path.append('/home/lenovo7/Downloads/manoharfinal/backend')

from app.infrastructure import create_infrastructure_request

async def test_create_request():
    # Generate unique ID each time
    unique_id = f"dev_aws_test_{uuid.uuid4().hex[:8]}"
    
    payload = {
        "request_identifier": unique_id,
        "user_email": "kadimisettimanoharreddy@gmail.com",
        "cloud_provider": "aws", 
        "environment": "dev",
        "resource_type": "ec2",
        "parameters": {
            "instance_type": "t3.micro",
            "region": "us-east-1",
            "operating_system": "ubuntu",
            "storage_size": 8
        }
    }
    
    print("Testing infrastructure request creation...")
    print(f"User email: {payload['user_email']}")
    print(f"Request ID: {payload['request_identifier']}")
    
    try:
        result = await create_infrastructure_request(payload)
        print(f"✅ SUCCESS: Created request {result}")
        print("✅ Check your Celery worker logs now!")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_create_request())