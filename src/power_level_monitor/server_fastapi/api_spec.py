from __future__ import annotations

from ese774_frame.api_spec import ApiSpec

from src.server_fastapi.api_models import BaselineRequest
from src.server_fastapi.api_models import BaselineResponse
from src.server_fastapi.api_models import BoolResponse
from src.server_fastapi.api_models import DetectorParamsRequest
from src.server_fastapi.api_models import DetectorParamsResponse
from src.server_fastapi.api_models import MeasurementResponse
from src.server_fastapi.api_models import MeasurementUpdateRequest
from src.server_fastapi.api_models import RoiPointsRequest
from src.server_fastapi.api_models import RoiPointsResponse
from src.server_fastapi.api_models import StatusResponse


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
        request_model=BaselineRequest,
        response_model=BoolResponse,
        method="post",
        summary="set_baseline",
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
        name="update_measurement",
        object_name=OBJECT_NAME,
        request_model=MeasurementUpdateRequest,
        response_model=BoolResponse,
        method="post",
        summary="update_measurement",
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