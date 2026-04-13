import random
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask


FIRST_NAMES = ["Liam", "Olivia", "Noah", "Emma", "Oliver", "Ava", "Elijah", "Sophia"]
LAST_NAMES = ["Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Lee"]

BOOKING_DATES = [
    ("2024-01-10", "2024-01-15"),
    ("2024-02-05", "2024-02-10"),
    ("2024-03-20", "2024-03-25"),
    ("2024-04-01", "2024-04-07"),
    ("2024-05-15", "2024-05-20"),
]

ADDITIONAL_NEEDS_OPTIONS = ["Breakfast", "Late checkout", "Early check-in", "Airport transfer", "None"]


class AdminUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self.token = None
        self.booking_ids = []
        self.managed_booking_ids = []  # Booking yang dibuat/dikelola oleh admin ini

        self._login()
        self._load_all_bookings()

    def _login(self):
        with self.client.post(
            "/auth",
            json={"username": "admin", "password": "password123"},
            headers={"Content-Type": "application/json"},
            name="/auth [login]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    token = data.get("token")
                    if token and token != "Bad credentials":
                        self.token = token
                        resp.success()
                    else:
                        resp.failure("Login gagal: Bad credentials")
                except Exception:
                    resp.failure("Response auth tidak valid")
            else:
                resp.failure(f"Auth error: {resp.status_code}")

    def _load_all_bookings(self):
        """Helper: muat semua booking ID."""
        with self.client.get(
            "/booking",
            name="/booking [admin load]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    self.booking_ids = [item["bookingid"] for item in data if "bookingid" in item]
                    resp.success()
                except Exception:
                    resp.failure("Gagal parse daftar booking")
            else:
                resp.failure(f"Load booking gagal: {resp.status_code}")

    def _get_auth_headers(self):
        """Kembalikan header dengan cookie token untuk operasi yang butuh auth."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": f"token={self.token}"
        }

    # -------------------------------------------------------------------------
    # TASK 1 (weight 3): Monitor semua booking — paling sering
    # -------------------------------------------------------------------------
    @task(3)
    def monitor_all_bookings(self):
        """GET /booking — admin memantau semua reservasi aktif."""
        with self.client.get(
            "/booking",
            name="/booking [monitor]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    self.booking_ids = [item["bookingid"] for item in data if "bookingid" in item]
                    resp.success()
                except Exception:
                    resp.failure("Response tidak valid")
            else:
                resp.failure(f"Monitor gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 2 (weight 2): Lihat detail booking spesifik
    # -------------------------------------------------------------------------
    @task(2)
    def view_booking_detail(self):
        """GET /booking/{id} — admin membuka detail booking untuk review."""
        if not self.booking_ids:
            self._load_all_bookings()
            raise RescheduleTask()

        booking_id = random.choice(self.booking_ids)
        with self.client.get(
            f"/booking/{booking_id}",
            name="/booking/{id} [admin view]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 404:
                self.booking_ids = [bid for bid in self.booking_ids if bid != booking_id]
                resp.success()
            else:
                resp.failure(f"View detail gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 3 (weight 2): Buat booking baru atas nama tamu
    # -------------------------------------------------------------------------
    @task(2)
    def create_booking_for_guest(self):
        """POST /booking — admin input reservasi baru dari tamu walk-in."""
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        checkin, checkout = random.choice(BOOKING_DATES)

        payload = {
            "firstname": fname,
            "lastname": lname,
            "totalprice": random.randint(150, 800),
            "depositpaid": True,
            "bookingdates": {
                "checkin": checkin,
                "checkout": checkout
            },
            "additionalneeds": random.choice(ADDITIONAL_NEEDS_OPTIONS)
        }

        with self.client.post(
            "/booking",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            name="/booking [admin create]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    new_id = data.get("bookingid")
                    if new_id:
                        self.managed_booking_ids.append(new_id)
                    resp.success()
                except Exception:
                    resp.failure("Response create tidak valid")
            else:
                resp.failure(f"Create gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 4 (weight 1): Partial update (PATCH) booking — ubah needs/harga
    # -------------------------------------------------------------------------
    @task(1)
    def partial_update_booking(self):
        """PATCH /booking/{id} — admin update sebagian data booking (misal: tambahan kebutuhan)."""
        if not self.token:
            self._login()
            raise RescheduleTask()

        # Prioritaskan update booking yang dikelola sendiri, fallback ke semua booking
        target_ids = self.managed_booking_ids if self.managed_booking_ids else self.booking_ids
        if not target_ids:
            raise RescheduleTask()

        booking_id = random.choice(target_ids)
        patch_payload = {
            "additionalneeds": random.choice(ADDITIONAL_NEEDS_OPTIONS),
            "totalprice": random.randint(150, 800)
        }

        with self.client.patch(
            f"/booking/{booking_id}",
            json=patch_payload,
            headers=self._get_auth_headers(),
            name="/booking/{id} [partial update]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 403:
                # Token expired, login ulang
                self._login()
                resp.failure("Token expired, re-login")
            elif resp.status_code == 404:
                # Booking sudah tidak ada
                if booking_id in self.managed_booking_ids:
                    self.managed_booking_ids.remove(booking_id)
                resp.success()
            else:
                resp.failure(f"Patch gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 5 (weight 1): Full update (PUT) booking — ubah semua data
    # -------------------------------------------------------------------------
    @task(1)
    def full_update_booking(self):
        """PUT /booking/{id} — admin update lengkap data booking (misal: reschedule)."""
        if not self.token:
            self._login()
            raise RescheduleTask()

        target_ids = self.managed_booking_ids if self.managed_booking_ids else self.booking_ids
        if not target_ids:
            raise RescheduleTask()

        booking_id = random.choice(target_ids)
        checkin, checkout = random.choice(BOOKING_DATES)

        put_payload = {
            "firstname": random.choice(FIRST_NAMES),
            "lastname": random.choice(LAST_NAMES),
            "totalprice": random.randint(150, 800),
            "depositpaid": True,
            "bookingdates": {
                "checkin": checkin,
                "checkout": checkout
            },
            "additionalneeds": random.choice(ADDITIONAL_NEEDS_OPTIONS)
        }

        with self.client.put(
            f"/booking/{booking_id}",
            json=put_payload,
            headers=self._get_auth_headers(),
            name="/booking/{id} [full update]",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 403:
                self._login()
                resp.failure("Token expired, re-login")
            elif resp.status_code == 404:
                if booking_id in self.managed_booking_ids:
                    self.managed_booking_ids.remove(booking_id)
                resp.success()
            else:
                resp.failure(f"PUT gagal: {resp.status_code}")

    # -------------------------------------------------------------------------
    # TASK 6 (weight 1): Hapus booking — paling jarang
    # -------------------------------------------------------------------------
    @task(1)
    def delete_booking(self):
        """DELETE /booking/{id} — admin menghapus reservasi yang sudah selesai."""
        if not self.token:
            self._login()
            raise RescheduleTask()

        # Hanya hapus booking yang dibuat sendiri untuk menghindari konflik antar user
        if not self.managed_booking_ids:
            raise RescheduleTask()

        booking_id = self.managed_booking_ids.pop(0)  # FIFO: hapus yang paling lama

        with self.client.delete(
            f"/booking/{booking_id}",
            headers=self._get_auth_headers(),
            name="/booking/{id} [delete]",
            catch_response=True
        ) as resp:
            if resp.status_code == 201:
                # Restful-booker mengembalikan 201 untuk DELETE sukses (quirk API ini)
                resp.success()
            elif resp.status_code == 403:
                self._login()
                resp.failure("Token expired saat delete")
            elif resp.status_code == 404:
                resp.success()  # Sudah terhapus sebelumnya
            else:
                resp.failure(f"Delete gagal: {resp.status_code}")


# -------------------------------------------------------------------------
# Event hook: log summary saat test selesai
# -------------------------------------------------------------------------
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n===== ADMIN JOURNEY TEST SELESAI =====")