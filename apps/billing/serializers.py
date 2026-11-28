from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Plan


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
    