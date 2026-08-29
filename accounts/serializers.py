from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

PASSWORD_INPUT_STYLE = {'input_type': 'password'}
PASSWORDS_DO_NOT_MATCH = 'Passwords do not match.'


def password_field(**kwargs: Any) -> serializers.CharField:
    """Build a write-only ``CharField`` rendered as a password input."""
    kwargs.setdefault('required', True)
    kwargs.setdefault('write_only', True)
    return serializers.CharField(style=PASSWORD_INPUT_STYLE, **kwargs)


def validate_password_strength(
    password: str,
    user: Any = None,
    field_name: str | None = None,
) -> str:
    """Run Django's password validators and re-raise failures as DRF errors."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        messages = list(exc.messages)
        raise serializers.ValidationError(
            {field_name: messages} if field_name else messages
        ) from exc
    return password


class PasswordPairMixin:
    """Validate a ``password`` + confirmation pair on a serializer.

    Subclasses only need to declare the two fields and, if they use different
    names, override ``password_field_name`` / ``confirm_field_name``.
    """

    password_field_name = 'new_password'
    confirm_field_name = 'new_password_confirm'

    def get_password_validation_user(self) -> Any:
        """User passed to Django's validators (enables similarity checks)."""
        return None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        password = attrs.get(self.password_field_name)
        confirm = attrs.get(self.confirm_field_name)

        if password:
            validate_password_strength(
                password,
                user=self.get_password_validation_user(),
                field_name=self.password_field_name,
            )

        if password != confirm:
            raise serializers.ValidationError(
                {self.confirm_field_name: PASSWORDS_DO_NOT_MATCH}
            )

        return attrs


class BaseUserSerializer(serializers.ModelSerializer):
    """Shared user fields and behaviour."""

    full_name = serializers.CharField(
        source='get_full_name',
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'department', 'is_available',
            'job_title', 'date_joined',
        )
        read_only_fields = ('id', 'date_joined')

class UserSerializer(BaseUserSerializer):
    """Compact user serializer for list views."""


class UserPublicSerializer(serializers.ModelSerializer):
    """Public user data — safe to expose to any authenticated user.

    Excludes email, phone_number, bio, last_login, hourly_rate. Use
    UserDetailSerializer for admin/manager/owner reads.
    """

    class Meta:
        model = User
        fields = (
            'id', 'username', 'first_name', 'last_name',
            'role', 'department', 'is_available',
            'job_title', 'profile_picture',
        )
        read_only_fields = fields


class UserDetailSerializer(BaseUserSerializer):
    """Detailed user serializer for retrieve and profile views."""


class UserRegistrationSerializer(PasswordPairMixin, serializers.ModelSerializer):
    """Serializer for user registration."""

    password_field_name = 'password'
    confirm_field_name = 'password_confirm'

    password = password_field()
    password_confirm = password_field()

    class Meta:
        model = User
        fields = (
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name',
        )
        extra_kwargs = {
            'email': {'required': True, 'allow_blank': False},
        }

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        # PR-4 L-1: do NOT distinguish "email already exists" from other
        # failures. The error message below is generic on purpose to
        # prevent email-enumeration on the registration endpoint.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'Registration failed. Please try again.'
            )
        return value

    def create(self, validated_data: dict[str, Any]) -> Any:
        validated_data.pop(self.confirm_field_name, None)
        return User.objects.create_user(**validated_data)


class NewPasswordSerializer(PasswordPairMixin, serializers.Serializer):
    """Base serializer for flows that set a new password."""

    new_password = password_field()
    new_password_confirm = password_field()


class ChangePasswordSerializer(NewPasswordSerializer):
    """Serializer for password change by an authenticated user."""

    old_password = password_field()

    def get_password_validation_user(self) -> Any:
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'new_password': 'New password must be different from old password.'
            })
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""

    email = serializers.EmailField(required=True)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmSerializer(NewPasswordSerializer):
    """Serializer for password reset confirmation."""

    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)


class LogoutSerializer(serializers.Serializer):
    """Serializer for logout."""

    refresh = serializers.CharField(required=False)
    logout_all = serializers.BooleanField(default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get('refresh') and not attrs.get('logout_all'):
            raise serializers.ValidationError(
                'Either refresh token or logout_all must be provided.'
            )
        return attrs


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Token serializer that adds user data to the token and the response."""

    @staticmethod
    def _user_claims(user: Any) -> dict[str, Any]:
        return {
            'username': user.username,
            'role': user.role,
        }

    @classmethod
    def get_token(cls, user: Any) -> Any:
        token = super().get_token(user)
        for key, value in cls._user_claims(user).items():
            token[key] = value
        return token

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.pk,
            **self._user_claims(self.user),
            'full_name': self.user.get_full_name(),
        }
        return data

    