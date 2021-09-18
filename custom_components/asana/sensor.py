"""Provides Asana Tasks sensor data."""

import collections
import datetime
import logging
import re

from homeassistant import const
from homeassistant.helpers import config_validation
from homeassistant.helpers import entity
import requests
import voluptuous


_DEFAULT_NAME = 'asana'

_ASANA_API_URL = 'https://app.asana.com/api/1.0'
_ASANA_API_TASK_FIELDS = 'id,name,created_at,due_on,completed,completed_at'

_ASANA_TIMEFRAME_NAME = 'timeframe'
_ASANA_TIMEFRAME_COMPLETED = 'past'
_ASANA_TIMEFRAME_NOT_COMPLETED = 'future'
_ASANA_TIMEFRAMES = [_ASANA_TIMEFRAME_COMPLETED, _ASANA_TIMEFRAME_NOT_COMPLETED]

_ASANA_SENSOR_NAME = 'name'

_ASANA_SENSOR_TYPE_NAME = 'sensor_type'
_ASANA_SENSOR_TYPE_COUNTER = 'counter'
_ASANA_SENSOR_TYPE_LIST = 'list'
_ASANA_SENSOR_TASK_TYPES = [_ASANA_SENSOR_TYPE_COUNTER, _ASANA_SENSOR_TYPE_LIST]

_ASANA_TASK_DATE_NAME = 'task_date'
_ASANA_TASK_DATE_ALL = 'all'


_CONFIG_WORKSPACE = 'workspace'

PLATFORM_SCHEMA = config_validation.PLATFORM_SCHEMA.extend({
    voluptuous.Required(const.CONF_ACCESS_TOKEN): config_validation.string,
    voluptuous.Required(_CONFIG_WORKSPACE): config_validation.string,
    voluptuous.Required(
        const.CONF_MONITORED_VARIABLES): config_validation.ensure_list,
    voluptuous.Optional(
        const.CONF_NAME, default=_DEFAULT_NAME): config_validation.string,
})


async def setup(hass, config):
  """No set up required once token is obtained."""
  return True

def setup_platform(hass, config, add_devices, discovery_info=None):
  """Adds sensor platform to the list of platforms."""
  setup(hass, config)
  add_devices([AsanaTaskSensor(config)], True)


class AsanaTaskApi(object):
  """API class to retrieve data from Asana."""

  def __init__(self, token, workspace, since_days_ago=0):
    """Initializes API reader.

    Args:
      token: Individual API token.
    """
    self._token = token
    self._workspace = workspace
    self._since_days_ago = since_days_ago

  def _get_since_date(self):
    """Gets since date based on days ago.

    Return:
      Current date (YYYY-MM-DD) minus since days ago.
    """
    today = datetime.date.today()
    fetch_date = today - datetime.timedelta(days=self._since_days_ago)
    return fetch_date.strftime('%Y-%m-%d')

  def _get_api_endpoint(self):
    """Gets API endpoint for Asana tasks.

    Returns:
      Asana Taks API endpoint URL.
    """
    return (
        '{api_url}/tasks?'
        'workspace={workspace}'
        '&assignee=me'
        '&opt_fields={api_fields}'
        '&completed_since={since_date}'
        '&limit=100'
    ).format(
        api_url=_ASANA_API_URL,
        api_fields=_ASANA_API_TASK_FIELDS,
        since_date=self._get_since_date(),
        workspace=self._workspace,
    )

  def get_api_data(self):
    """Fetches data for a given Asana endpoint.

    Returns:
      Dictionary containing tasks data.
    """
    tasks_data = []
    api_url = self._get_api_endpoint()

    while api_url:
      response = requests.get(
          api_url,
          headers={'Authorization': 'Bearer {}'.format(self._token)}
      )
      response_data = response.json()

      if not response_data or 'data' not in response_data:
        logging.error('Response not expected.')
        return None
      tasks_data.extend(response_data.get('data', []))

      # This will be None unless a next page token is retrieved.
      next_page = response_data.get('next_page')
      api_url = next_page.get('uri') if next_page else None

    return tasks_data


class AsanaTaskSensor(entity.Entity):
  """Representation of an Asana Task sensor."""

  def __init__(self, config):
    """Initialize the sensor."""

    # Sensor internals.
    self._state_attribute_name = None
    self._monitored_variables = self._process_monitored_variables(
        config.get(const.CONF_MONITORED_VARIABLES))

    # API Internals.
    token = config.get(const.CONF_ACCESS_TOKEN)
    workspace = config.get(_CONFIG_WORKSPACE)
    since_days_ago = self._get_max_since_days_ago()
    self._api = AsanaTaskApi(token, workspace, since_days_ago)
    self._task_data = {}

    # Metadata.
    self._name = config.get(const.CONF_NAME)

    # Attributes.
    self._attributes = {
      variable: None for variable in self._monitored_variables.keys()
    }
    self._state = None

  def _process_monitored_variables(self, monitored_variables):
    """Processes monitored variables in string format.

    Returns:
      Dictionary of dictionaries with monitored variable data.
    """
    new_monitored_variables = {}
    for variable in monitored_variables:
      variable = variable.lower()
      variable_parts = variable.split('_')
      (variable_type, variable_timeframe, _) = variable_parts
      variable_days = self._get_days_from_monitored_variable(variable)

      if variable_days is None:
        logging.error(
            'Invalid date range in monitored variables: {}'.format(variable))
        continue

      if variable_type not in _ASANA_SENSOR_TASK_TYPES:
        logging.error(
            'Invalid attribute type in monitored variables: {}'.format(variable))
        continue

      if variable_timeframe not in _ASANA_TIMEFRAMES:
        logging.error(
            'Invalid timeframe in monitored variables: {}'.format(variable))
        continue

      if self._state_attribute_name is None:
        self._state_attribute_name = variable

      new_monitored_variables[variable] = {
          _ASANA_SENSOR_NAME: variable,
          _ASANA_SENSOR_TYPE_NAME: variable_type,
          _ASANA_TIMEFRAME_NAME: variable_timeframe,
          _ASANA_TASK_DATE_NAME: variable_days,
      }

    return new_monitored_variables

  def _get_days_from_monitored_variable(self, monitored_variable):
    """Gets the number of days from monitored variable name.

    Args:
      monitored_variable: Monitored variable from which to get days.

    Returns:
      Days for monitored variable.
      'all' if all.
      None if error or not found.
    """
    if _ASANA_TASK_DATE_ALL in monitored_variable:
      return _ASANA_TASK_DATE_ALL
    match_days = re.search(r'(?:_)([\d]+)(?:day)',
                           monitored_variable, re.IGNORECASE)
    if not match_days:
      return None
    return int(match_days.groups()[0])

  def _get_max_since_days_ago(self):
    """Gets max amount of since days ago from monitored variables."""
    max_days_ago = 0
    for variable_config in self._monitored_variables.values():
      variable_timeframe = variable_config.get(_ASANA_TIMEFRAME_NAME)
      if variable_timeframe == _ASANA_TIMEFRAME_NOT_COMPLETED:
        continue
      days_ago = variable_config.get(_ASANA_TASK_DATE_NAME)
      if days_ago == _ASANA_TASK_DATE_ALL:
        continue
      max_days_ago = max(days_ago, max_days_ago)
    return max_days_ago

  def _task_day_matches_timeframe(self, task_day, variable_timeframe,
                                  variable_date):
    """Verifies whether a certain task day meets variable requirements.

    Args:
      task_day: The day (YYYY-MM-DD) of the task to validate.
      variable_timeframe: Whether timeframe is in the future or past.
      variable_date: The day limit (YYYY-MM-DD) for the variable.

    Returns:
      True if conditions are past. False otherwise.
    """
    if variable_timeframe == _ASANA_TIMEFRAME_COMPLETED:
      if task_day == _ASANA_TASK_DATE_ALL:
        return False
      return task_day >= variable_date

    elif variable_timeframe == _ASANA_TIMEFRAME_NOT_COMPLETED:
      if variable_date == _ASANA_TASK_DATE_ALL:
        return True
      return task_day <= variable_date

    return False

  def update(self):
    """Fetches data from API."""
    tasks_data = self._api.get_api_data()

    if tasks_data is None:
      logging.error('Error fetching Asana API data.')
      return

    self._store_task_data(tasks_data)
    self._update_sensor_attributes()
    self._update_sensor_state()

  def _store_task_data(self, tasks_data):
    """Stores data from tasks from API in a by-date structure.

    Args:
      tasks_data: Lists of tasks from Asana API.

    Returns:
      Dictionary containing task lists by date and completion.
    """
    self._task_data = {
        _ASANA_TIMEFRAME_COMPLETED: {},
        _ASANA_TIMEFRAME_NOT_COMPLETED: {},
    }

    for task in tasks_data:
      if task.get('completed'):
        task_group = _ASANA_TIMEFRAME_COMPLETED
        task_date = (
            # Extracts YYYY-MM-DD in the simplest way possible.
            task.get('completed_at')[0:10] if task.get('completed_at')
            else _ASANA_TASK_DATE_ALL
        )
      else:
        task_group = _ASANA_TIMEFRAME_NOT_COMPLETED
        task_date = (
            # Extracts YYYY-MM-DD in the simplest way possible.
            task.get('due_on')[0:10] if task.get('due_on')
            else _ASANA_TASK_DATE_ALL
        )

      if task_date not in self._task_data[task_group]:
        self._task_data[task_group][task_date] = []

      task_name = (
          task.get('name')
          if task_date == _ASANA_TASK_DATE_ALL else
          '{} - {}'.format(task_date, task.get('name'))
      )
      self._task_data[task_group][task_date].append(task_name)

    return self._task_data

  def _update_sensor_attributes(self):
    """Updates monitored variables values."""
    for variable_name, variable_config in self._monitored_variables.items():
      variable_timeframe = variable_config.get(_ASANA_TIMEFRAME_NAME)
      selected_tasks_data = self._task_data.get(variable_timeframe, {})

      variable_days = variable_config.get(_ASANA_TASK_DATE_NAME)
      if variable_days == _ASANA_TASK_DATE_ALL:
        variable_date = variable_days
      else:
        date_difference = datetime.timedelta(days=variable_days)
        today = datetime.date.today()
        variable_date = (
          today - date_difference
          if variable_timeframe == _ASANA_TIMEFRAME_COMPLETED
          else today + date_difference
        ).strftime('%Y-%m-%d')

      matching_task_list = []
      for task_day in sorted(selected_tasks_data.keys()):
        if self._task_day_matches_timeframe(
            task_day, variable_timeframe, variable_date):
          matching_task_list.extend(selected_tasks_data[task_day])

      variable_type = variable_config.get(_ASANA_SENSOR_TYPE_NAME)
      self._attributes[variable_name] = (
          matching_task_list if variable_type == _ASANA_SENSOR_TYPE_LIST
          else len(matching_task_list)
      )

  def _update_sensor_state(self):
    """Updates the state of the sensor.

    By default uses the first monitored variable value.
    If no monitored variables, just sets as "OK".
    """
    self._state = (
        self._attributes[self._state_attribute_name]
        if self._state_attribute_name else 'OK'
    )

  # Hass.io properties.
  @property
  def name(self):
    """Return the name of the sensor."""
    return self._name

  @property
  def state(self):
    """Return the state of the sensor."""
    return self._state

  @property
  def device_state_attributes(self):
    """Return the sensor attributes."""
    return self._attributes
