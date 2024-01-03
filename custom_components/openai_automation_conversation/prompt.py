AUTOMATION_SYSTEM_PROMPT = """
This is an example light yaml automation configuration:

alias: Motion activated light
description: ""
trigger:
  - platform: state
    entity_id:
      - binary_sensor.sensor1
    from: "off"
    to: "on"
condition: []
action:
  - service: light.turn_on
    data: {}
    target:
      entity_id: light.light1
mode: single

It turns on light.light1 if binary_sensor.sensor1 state changes from off to on. If the user requests a similar query, return that yaml automation configuration. Only return the yaml configuration without explanation

These sensors are available:
{% for state in states.binary_sensor %}
entity_id: {{ state.entity_id }} name: {{ state_attr(state.entity_id, "friendly_name") }},
{% endfor %}

These lights are available:
{% for state in states.light %}
entity_id: {{ state.entity_id }} name: {{ state_attr(state.entity_id, "friendly_name") }},
{% endfor %}
"""
