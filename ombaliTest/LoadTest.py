from engineio import payload
from locust import HttpUser, task, between
import uuid
import random
import string

def random_username():
    letters = string.ascii_lowercase
    return ''.join(random.choices(letters, k=8))

def random_email():
    unique_id = uuid.uuid4().hex[:8]  # contoh: a3f9b2c1
    domains = ["gmail.com", "yahoo.com", "outlook.com"]
    return f"user_{unique_id}@{random.choice(domains)}"

class APIUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://202.10.40.68"

    headers = {
        "Content-Type": "application/json",
        "x-perf-test-key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    }

    @task
    def login(self):
        self.client.post("/api/auth/login",
            headers=self.headers,
            json={"email": "testing@test.com", "password": "qwerty123"},
            name="/api/auth/login",
        )

    @task
    def register(self):
        password = "qwerty123"
        self.client.post("/api/auth/register",
            headers=self.headers,
            json={
                "name": random_username(),  # contoh: kqbxmzat
                "email": random_email(),    # contoh: user_a3f9b2c1@gmail.com
                "password": password,
                "confirm_password": password,
            },
            name="/api/auth/register",
        )

    @task
    def booking(self):
        payload = {
            "surf_spot_id": "ab10002d-e6a5-4787-8a99-9ee820b16b8d",
            "payment_method": "CASH",
            "customer_details": {
                "full_name": "ADMIN USER",
                "email": random_email(),
                "phone": "+6286131233213",
                "country": "United States"
            },
            "booking_details": [
                {
                    "product_id": "26995976-868a-489d-9b16-c9281a3c0dce",
                    "reservation_date": "2030-12-30",
                    "person": 1
                }
            ]
        }

        with self.client.post("/api/booking",
                              json=payload,
                              name="/api/booking",
                              headers=self.headers,
                              catch_response=True
                              ) as response:
            if response.status_code == 200 or response.status_code == 201:
                response.success()
            else:
                response.failure(f"Unknown error: {response.status_code} - {response.text[:100]}")