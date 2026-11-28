from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    yearly_discount_percent = serializers.IntegerField(read_only=True)
    limits = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "code",
            "name",
            "description",
            "audience",
            "currency",
            "price_monthly",
            "price_yearly",
            "yearly_discount_percent",
            "trial_days",
            "limits",
            "features",
        ]
        read_only_fields = fields

    @extend_schema_field(
        {
            "type": "object",
            "description": "Cheklovlar. null = cheksiz.",
            "properties": {
                "branches": {"type": "integer", "nullable": True},
                "staff": {"type": "integer", "nullable": True},
                "students": {"type": "integer", "nullable": True},
            },
        }
    )
    def get_limits(self, plan):
        return plan.limits

    @extend_schema_field(
        {
            "type": "object",
            "description": "Barcha imkoniyatlar: {kalit: true/false}.",
            "additionalProperties": {"type": "boolean"},
        }
    )
    def get_features(self, plan):
        return plan.feature_map()


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    status = serializers.SerializerMethodField()
    is_trial = serializers.BooleanField(read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "is_trial",
            "trial_started_at",
            "trial_ends_at",
            "days_left",
            "created_at",
        ]
        read_only_fields = fields

    def get_status(self, subscription) -> str:
        # Vaqt bo'yicha hisoblangan holat: yopish buyrug'i kechiksa ham to'g'ri.
        return subscription.effective_status()

    def get_days_left(self, subscription) -> int:
        return subscription.days_left()


class SubscriptionStateSerializer(serializers.Serializer):
    subscription = SubscriptionSerializer(allow_null=True)
    trial_available = serializers.BooleanField()


class StartTrialSerializer(serializers.Serializer):
    plan = serializers.SlugField(max_length=40, help_text="Tarif kodi")
