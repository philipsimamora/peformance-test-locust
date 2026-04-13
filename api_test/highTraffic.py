from locust import HttpUser, task, between

class BookerUser(HttpUser):
    wait_time = between(1, 2)

    host = 'https://restful-booker.herokuapp.com'

    @task
    def get_booking_ids(self):
        with self.client.get("/booking", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Gagal mendapatkan data: {response.status_code}")