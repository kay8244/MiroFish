"""
Zep 클라이언트 팩토리
Cloud / 자체 호스팅(CE) 모두 지원
"""

from zep_cloud.client import Zep
from ..config import Config


def create_zep_client(api_key: str = None) -> Zep:
    """
    Zep 클라이언트 생성.
    ZEP_BASE_URL이 설정되어 있으면 자체 호스팅(CE)으로 연결,
    없으면 Zep Cloud로 연결.
    """
    key = api_key or Config.ZEP_API_KEY
    base_url = Config.ZEP_BASE_URL

    if base_url:
        return Zep(api_key=key, base_url=base_url)
    else:
        return Zep(api_key=key)
