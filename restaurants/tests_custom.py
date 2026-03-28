import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from .models import RestaurantDataModel, TableReservation
from .serializers import TableReservationSerializer

User = get_user_model()

class RestaurantIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.restaurant = RestaurantDataModel.objects.create(
            name="Test Restaurant",
            area="Test Area",
            city="Test City",
            is_open=True,
            opening_time=datetime.time(9, 0),
            closing_time=datetime.time(22, 0),
            total_tables=10
        )

    def test_table_reservation_capacity_sync(self):
        """Test if table_capacity is synchronized with number_of_guests on save."""
        reservation = TableReservation.objects.create(
            user=self.user,
            restaurant=self.restaurant,
            reservation_date=datetime.date.today(),
            reservation_time=datetime.time(12, 0),
            number_of_guests=6
        )
        self.assertEqual(reservation.table_capacity, 6)

        reservation.number_of_guests = 8
        reservation.save()
        self.assertEqual(reservation.table_capacity, 8)

    def test_operating_hours_validation(self):
        """Test if reservation time is validated against restaurant operating hours."""
        # Valid time
        data = {
            'restaurant': self.restaurant.id,
            'reservation_date': datetime.date.today() + datetime.timedelta(days=1),
            'reservation_time': '12:00',
            'number_of_guests': 4
        }
        serializer = TableReservationSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        # Invalid time (too early)
        data_early = data.copy()
        data_early['reservation_time'] = '08:00'
        serializer_early = TableReservationSerializer(data=data_early)
        with self.assertRaises(ValidationError) as cm:
            serializer_early.is_valid(raise_exception=True)
        self.assertIn("operating hours", str(cm.exception))

        # Invalid time (too late)
        data_late = data.copy()
        data_late['reservation_time'] = '23:00'
        serializer_late = TableReservationSerializer(data=data_late)
        with self.assertRaises(ValidationError) as cm:
            serializer_late.is_valid(raise_exception=True)
        self.assertIn("operating hours", str(cm.exception))

    def test_closed_restaurant_validation(self):
        """Test if closed restaurant is validated."""
        self.restaurant.is_open = False
        self.restaurant.save()

        data = {
            'restaurant': self.restaurant.id,
            'reservation_date': datetime.date.today() + datetime.timedelta(days=1),
            'reservation_time': '12:00',
            'number_of_guests': 4
        }
        serializer = TableReservationSerializer(data=data)
        with self.assertRaises(ValidationError) as cm:
            serializer.is_valid(raise_exception=True)
        self.assertIn("currently closed", str(cm.exception))
