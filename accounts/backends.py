from django.contrib.auth import get_user_model


class PhoneBackend:
    """Sign in with a phone number alone (no password).

    Only regular accounts qualify: staff and superusers must always present a
    password (handled by ``ModelBackend``), so the admin is never reachable
    with just a phone number. Callers that also pass a ``password`` are left to
    ``ModelBackend`` and get ``None`` here.
    """

    def authenticate(self, request, phone=None, **kwargs):
        if phone is None or "password" in kwargs:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return None
        if user.is_staff or user.is_superuser or not user.is_active:
            return None
        return user

    def get_user(self, user_id):
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if user.is_active else None
