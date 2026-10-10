"""Request validation. Messages are shown to the user next to the field."""

from rest_framework import serializers


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer(error_messages={"required": "Choose a starting point from the list."})
    destination = PlaceSerializer(error_messages={"required": "Choose a destination from the list."})
    departure = serializers.DateTimeField(
        error_messages={
            "required": "Pick a departure date and time.",
            "invalid": "Enter a valid departure date and time.",
        }
    )
    load_lb = serializers.FloatField(
        min_value=0,
        max_value=80_000,
        error_messages={
            "required": "Enter the load weight in pounds.",
            "invalid": "Load weight must be a number of pounds.",
            "min_value": "Load weight cannot be negative.",
            "max_value": "Load weight must be 80,000 lb or less (the US legal gross limit).",
        },
    )
    interval_mi = serializers.ChoiceField(
        choices=[10, 25, 50],
        default=25,
        error_messages={"invalid_choice": "Checkpoint spacing must be 10, 25 or 50 miles."},
    )


class HeatmapRequestSerializer(serializers.Serializer):
    lines = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
            min_length=2,
            max_length=20_000,
        ),
        min_length=1,
        max_length=6,
    )
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=80_000)
