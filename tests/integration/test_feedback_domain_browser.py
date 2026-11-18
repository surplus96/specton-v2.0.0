"""Mail→approval→domain application→preview→document comparison→adoption in Chromium."""

import pytest
from test_feedback_browser import connected as connected
from test_feedback_browser import settings as settings
from test_feedback_browser import test_browser_mail_to_adoption as test_browser_mail_to_adoption
from test_feedback_browser import verified as verified
from test_feedback_browser import workspace as workspace
from test_feedback_consistency import source as source

pytestmark = [pytest.mark.db, pytest.mark.docker_browser]
