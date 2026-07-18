from __future__ import annotations

from ese774_frame.api_spec import ApiSpec

from power_level_monitor.server_fastapi.api_models import BaselineResponse
from power_level_monitor.server_fastapi.api_models import BoolResponse
from power_level_monitor.server_fastapi.api_models import DetectorParamsRequest
from power_level_monitor.server_fastapi.api_models import DetectorParamsResponse
from power_level_monitor.server_fastapi.api_models import MeasurementResponse
from power_level_monitor.server_fastapi.api_models import RoiPointsRequest
from power_level_monitor.server_fastapi.api_models import RoiPointsResponse
from power_level_monitor.server_fastapi.api_models import StatusResponse


OBJECT_NAME = "powder_control"


API_SPEC = [
    ApiSpec(
        name="connect",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="connect",
    ),
    ApiSpec(
        name="disconnect",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="disconnect",
    ),
    ApiSpec(
        name="start",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="start",
    ),
    ApiSpec(
        name="stop",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="stop",
    ),
    ApiSpec(
        name="process_once",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="process_once",
    ),
    ApiSpec(
        name="get_status",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=StatusResponse,
        method="get",
        summary="get_status",
    ),
    ApiSpec(
        name="set_roi_points",
        object_name=OBJECT_NAME,
        request_model=RoiPointsRequest,
        response_model=BoolResponse,
        method="post",
        summary="set_roi_points",
    ),
    ApiSpec(
        name="get_roi_points",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=RoiPointsResponse,
        method="get",
        summary="get_roi_points",
    ),
    ApiSpec(
        name="clear_roi_points",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="clear_roi_points",
    ),
    ApiSpec(
        name="set_baseline",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="set_baseline",
    ),
    ApiSpec(
        name="clear_baseline",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BoolResponse,
        method="post",
        summary="clear_baseline",
    ),
    ApiSpec(
        name="get_baseline",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=BaselineResponse,
        method="get",
        summary="get_baseline",
    ),
    ApiSpec(
        name="set_detector_params",
        object_name=OBJECT_NAME,
        request_model=DetectorParamsRequest,
        response_model=BoolResponse,
        method="post",
        summary="set_detector_params",
    ),
    ApiSpec(
        name="get_detector_params",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=DetectorParamsResponse,
        method="get",
        summary="get_detector_params",
    ),
    ApiSpec(
        name="get_measurement",
        object_name=OBJECT_NAME,
        request_model=None,
        response_model=MeasurementResponse,
        method="get",
        summary="get_measurement",
    ),
]
