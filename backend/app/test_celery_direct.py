# test_celery_direct.py
import sys
sys.path.append('/home/lenovo7/Downloads/manoharfinal/backend')

from app.tasks import process_infrastructure_request

print("Testing direct Celery task dispatch...")

try:
    result = process_infrastructure_request.delay("test_direct_123", "kadimisettimanoharreddy@gmail.com")
    print(f"Task dispatched with ID: {result.id}")
    print("Check your Celery worker logs now!")
except Exception as e:
    print(f"Failed to dispatch task: {e}")
    import traceback
    traceback.print_exc()