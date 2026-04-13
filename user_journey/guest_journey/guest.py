import random
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask


FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona", "George", "Hannah"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]

CHECK_IN_DATES = [
    ("2025-06-01", "2025-06-05"),
    ("2025-07-10", "2025-07-15"),
    ("2025-08-20", "2025-08-25"),
    ("2025-09-01", "2025-09-07"),
    ("2025-10-12", "2025-10-18"),
]


class GuestUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.booking_ids = []
        self.my_booking_id = None

        self._load_booking_list()

    def _load_booking_list(self):
        with self.client.get(
            "/booking",
            name="/booking [initial load]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    self.booking_ids = [item["bookingid"] for item in data if "bookingid" in item]
                    resp.success()
                except Exception:
                    resp.failure("Gagal parse JSON daftar booking")
            else:
                resp.failure(f"Status {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 1 (weight 3): Browse daftar booking — paling sering dilakukan
    # -------------------------------------------------------------------------
    @task(3)
    def browse_booking_list(self):
        """GET /booking — tamu melihat semua reservasi yang tersedia."""
        with self.client.get("/booking", name="/booking [browse]", catch_response=True) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # Simpan ID terbaru untuk dipakai task lain
                    self.booking_ids = [item["bookingid"] for item in data if "bookingid" in item]
                    resp.success()
                except Exception:
                    resp.failure("Response bukan JSON valid")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 2 (weight 2): Lihat detail satu booking
    # -------------------------------------------------------------------------
    @task(2)
    def view_booking_detail(self):
        """GET /booking/{id} — tamu membuka detail satu reservasi."""
        if not self.booking_ids:
            self._load_booking_list()
            raise RescheduleTask()

        booking_id = random.choice(self.booking_ids)

        with self.client.get(
            f"/booking/{booking_id}",
            name="/booking/{id} [detail]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # Validasi field penting ada
                    required = ["firstname", "lastname", "totalprice", "bookingdates"]
                    missing = [f for f in required if f not in data]
                    if missing:
                        resp.failure(f"Field hilang: {missing}")
                    else:
                        resp.success()
                except Exception:
                    resp.failure("Response bukan JSON valid")
            elif resp.status_code == 404:
                # Booking sudah dihapus, refresh list
                self.booking_ids = [bid for bid in self.booking_ids if bid != booking_id]
                resp.success()  # Bukan failure sistem, hanya data stale
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 3 (weight 2): Filter booking berdasarkan nama
    # -------------------------------------------------------------------------
    @task(2)
    def search_booking_by_name(self):
        """GET /booking?firstname=X — tamu mencari booking berdasarkan nama depan."""
        name = random.choice(FIRST_NAMES)
        with self.client.get(
            f"/booking?firstname={name}",
            name="/booking?firstname= [search]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Search gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 4 (weight 1): Buat booking baru — jarang (1 kali dibanding 3 browse)
    # -------------------------------------------------------------------------
    @task(1)
    def create_new_booking(self):
        """POST /booking — tamu membuat reservasi baru."""
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        checkin, checkout = random.choice(CHECK_IN_DATES)
        price = random.randint(100, 500)

        payload = {
            "firstname": fname,
            "lastname": lname,
            "totalprice": price,
            "depositpaid": random.choice([True, False]),
            "bookingdates": {
                "checkin": checkin,
                "checkout": checkout
            },
            "additionalneeds": random.choice(["Breakfast", "Lunch", "Dinner", "None"])
        }

        with self.client.post(
            "/booking",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            name="/booking [create]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    self.my_booking_id = data.get("bookingid")
                    resp.success()
                except Exception:
                    resp.failure("Response create tidak valid")
            else:
                resp.failure(f"Create booking gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 5 (weight 1): Verifikasi booking yang baru dibuat
    # -------------------------------------------------------------------------
    @task(1)
    def verify_my_booking(self):
        """GET /booking/{id} — verifikasi booking yang tadi dibuat."""
        if not self.my_booking_id:
            # Belum punya booking sendiri, skip
            raise RescheduleTask()

        with self.client.get(
            f"/booking/{self.my_booking_id}",
            name="/booking/{id} [verify own]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 404:
                # Sudah expired/reset oleh server (reset tiap 10 menit)
                self.my_booking_id = None
                resp.success()
            else:
                resp.failure(f"Verify booking gagal: {resp.status_code}")


# -------------------------------------------------------------------------
# Event hook: log summary saat test selesai
# -------------------------------------------------------------------------
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n===== GUEST JOURNEY TEST SELESAI =====")
    stats = environment.stats.total
    print(f"Total requests : {stats.num_requests}")
    print(f"Total failures : {stats.num_failures}")
    print(f"Avg response   : {stats.avg_response_time:.0f} ms")
    print(f"RPS            : {stats.current_rps:.2f}")
    print("========================================\n")