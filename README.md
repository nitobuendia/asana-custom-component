# Asana - Custom Component for Home-Assisant

This project is a custom component for [Home-Assistant](https://home-assistant.io). The component/platform creates one sensor with multiple attributes which provides task details from Asana data.

## What Data Can Be Retrieved

### Type of data

1. Counter: counts number of tasks within a certain time range.
1. List: provides the due date and task name for the tasks within a certain range.

### Timeframe of data

1. Future: provides all tasks due within a certain amount of days from today (into the future). (Note: tasks due in the past and not completed are also included)
1. Past: provides all tasks completed within a certain amount of days from today (into the past).

### Assigned tasks

- Only tasks assigned to owner of the token and within one workspace can be retrieved.

## Configuration

### Schema

```yaml
sensor:
  - platform: asana
    access_token: 
    workspace: 
    monitored_variables:
```

### Parameters

#### access_token
Asana Personal Access Token can be generated as one off from the Developer App Console ([article](https://asana.com/guide/help/api/api#gl-access-tokens)).

#### workspace
Id of the workspace from which to obtain data. If you are interested in more than one workspace, you would need to create more than one sensor (with the current code).

To retrieve the id you can go to Asana, log in to the workspace from which you want data, Inspect source code and look for the metatag shard_id  and get the value within content (e.g. `<meta name="shard_id" content="637546372573727">`, the workspace would be 637546372573727. 

Alternatively, you can use [Asana API Explorer for Workspaces](https://asana.com/developers/api-reference/workspaces) and issue a request to `GET /workspaces`, include the id and name field and just copy the id/gid value for the workspace you are interested.

#### monitored_variables
List of data to monitor.

The variables have this format: `<type>_<timeframe>_<days>` where:
  - `<type>` must be `counter` (number of tasks) or `list` (array of tasks).
  - `<timeframe>` must be `future` (pending tasks) or `past` (completed tasks).
  - `<days>` must be an `integer+days` to specify time period (e.g. `1day`, `7days`, `120days`)

#### scan_interval
Optional, but recommended to set to avoid hitting the API too many times. Seconds in between updates. My configuration is updating it every 1 hour.

## Example

### Sensor Configuration
```
sensor:
  - platform: asana
    access_token: !secret asana_api_token
    workspace: '637546372573727'
    scan_interval: 3600  # 1h
    monitored_variables:
      - counter_future_0days
      - counter_future_1day
      - counter_future_7days
      - counter_future_30days
      - counter_future_all
      - list_future_0days
      - list_future_1day
      - list_future_7days
      - counter_past_0days
      - counter_past_1day
      - counter_past_7days
      - counter_past_30days
```

### Explanation
This would create one Asana sensor with 12 attributes:
- counter_future_0days: Number of pending tasks due today, or before today.
- counter_future_1day: Number of pending tasks due tomorrow, or before tomorrow.
- counter_future_7days: Number of pending tasks due within or before the next 7 days.
- counter_future_30days: Number of pending tasks due within or before the next 30 days.
- counter_future_all: Number of total pending tasks.
- list_future_0days: List (array) of pending tasks due today, or before today.
- list_future_1day: List (array) of pending tasks due tomorrow, or before tomorrow.
- list_future_7days: List (array) of pending tasks due within or before the next 7 days.
- counter_past_0days: Number of tasks completed today.
- counter_past_1day: Number of tasks completed within the last day (today and yesterday).
- counter_past_7days: Number of tasks completed within the last 7 days.
- counter_past_30days: Number of tasks completed within the last 30 days.

The state of the sensor will be the same as the first monitored variable. In this case, it would be the value of `counter_future_0days` (number of pending tasks due today, or before today).

### Sample Sensor Output

State: `5`

Attributes:
```json

{
  "counter_future_0days": 5,
  "counter_future_1day": 7,
  "counter_future_7days": 16,
  "counter_future_30days": 30,
  "counter_future_all": 144,
  "list_future_0days": [
    "2019-07-18 - Do a certain task, that is overdue",
    "2019-08-14 - Do another task, due today",
  ],
  "list_future_1day": [
    "2019-07-18 - Do a certain task, that is overdue",
    "2019-08-14 - Do another task, due today",
    "2019-08-15 - Another task, due tomorrow",
    "2019-08-15 - Yet another task, due tomorrow"
  ],
  "list_future_7days": [
    "2019-07-18 - Do a certain task, that is overdue",
    "2019-08-14 - Do another task, due today",
    "2019-08-15 - Another task, due tomorrow",
    "2019-08-15 - Yet another task, due tomorrow"
    "2019-08-17 - Additional task for another day",
    "2019-08-18 - Something else here",
    "2019-08-19 - Weekly planning",
    "2019-08-21 - This is still within 7 days"
  ],
  "counter_past_0days": 2,
  "counter_past_1day": 6,
  "counter_past_7days": 30,
  "counter_past_30days": 168,
  "friendly_name": "asana"
}
```

## Recommendations and Foot Notes

### One sensor approach
The component is designed to make as little calls to the API as possible and calculate sensor information over it. This is why all the data is displayed within one sensor. In order to minimize the calls even further, it is recommended

### Use template sensors if you require monitoring of attributes
While technically, it is possible to create several sensors so each would monitor one condition, that would mean increasing the API calls. As a result, it is better to create a sensor from the conditions using templates. For example: 

```yaml
- platform: template
  sensors:
    tasks_completed_7days:
      entity_id: sensor.asana
      friendly_name: 'Tasks Completed Last 7 Days'
      unit_of_measurement: tasks
      value_template: >
        {{ states.sensor.asana.attributes.counter_past_7days }}
      icon_template: 'mdi:clipboard-check-outline'
```

### Use template sensors if you want to have some calculations
The counters operates calculating including today. For example, if you add a `counter_past_1day`, it would count the tasks that were completed either yesterday or today. If you want only for one day, you can create two monitored conditions one for one day, and one for one day less and calculate the difference. For example, if you want to calculate how many tasks you completed last week, you could monitor: `counter_past_7days` and `counter_past_6days` and then create a template sensor:

```yaml
- platform: template
  sensors:
    tasks_completed_last_week:
      entity_id: sensor.asana
      friendly_name: 'Tasks Completed Last Week'
      unit_of_measurement: tasks
      value_template: >
        {{
          states.sensor.asana.attributes.counter_past_7days -
          states.sensor.asana.attributes.counter_past_6days
        }}
      icon_template: 'mdi:clipboard-check-outline'
```

### Why workspaces and assigned tasks are required
The component is not using Asana Search API, which is more powerful, because that is only for paying users. The workaround is using the Task list, which requires a workspace (and assignee) or a project or a user list. I have implemented workspace, because that is what worked best for my use case. However, you could edit the code to change workspace to a user list or other supported input system.
