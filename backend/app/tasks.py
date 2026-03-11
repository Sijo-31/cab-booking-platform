from .celery_worker import celery_app


@celery_app.task
def send_receipt_email(user_email, ride_id):
    print(f"Sending receipt for ride {ride_id} to {user_email}")