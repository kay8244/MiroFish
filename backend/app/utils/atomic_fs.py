"""
원자적 파일 시스템 연산 유틸리티

디렉토리 레벨 atomic rename을 제공하여 파이프라인 단계 산출물을
최종 디렉토리로 격리 이관한다. 기존 서비스 내부 쓰기 코드는 수정하지
않고, 오케스트레이터 경계에서만 이 유틸리티를 사용한다.

같은 파일시스템 내에서만 atomic 보장되므로 임시 디렉토리와 최종
디렉토리는 같은 mount point 하위에 배치해야 한다 (EXDEV 에러 방지).
"""

import os
import shutil
import errno
from pathlib import Path
from typing import Union

from ..utils.logger import get_logger

logger = get_logger('mirofish.atomic_fs')

PathLike = Union[str, Path]


class AtomicFSError(Exception):
    """atomic_fs 연산 실패"""
    pass


class CrossDeviceError(AtomicFSError):
    """src와 dst가 다른 파일시스템에 있음 (EXDEV)"""
    pass


def atomic_move_dir(src: PathLike, dst: PathLike, overwrite: bool = True) -> None:
    """
    디렉토리를 atomic하게 이동한다.

    os.replace()는 같은 파일시스템 내에서 atomic rename을 보장한다.
    src와 dst가 다른 파일시스템이면 EXDEV 에러가 발생하며 CrossDeviceError로
    변환되어 호출자가 명시적으로 처리할 수 있도록 한다.

    Args:
        src: 이동할 원본 디렉토리 경로
        dst: 목적지 디렉토리 경로
        overwrite: dst가 이미 존재할 때 덮어쓸지 여부. False인데 dst 존재 시
                   FileExistsError 발생.

    Raises:
        FileNotFoundError: src가 존재하지 않음
        FileExistsError: overwrite=False인데 dst 존재
        CrossDeviceError: src와 dst가 다른 파일시스템 (EXDEV)
        AtomicFSError: 기타 실패
    """
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        raise FileNotFoundError(f"src does not exist: {src}")

    if dst_path.exists():
        if not overwrite:
            raise FileExistsError(f"dst already exists: {dst}")
        # os.replace()는 빈 디렉토리만 덮어쓸 수 있으므로 비어있지 않으면 먼저 제거
        logger.debug(f"dst 존재, 제거 후 이동: {dst}")
        shutil.rmtree(dst_path)

    # 부모 디렉토리 보장
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.replace(str(src_path), str(dst_path))
        logger.debug(f"atomic move 완료: {src} -> {dst}")
    except OSError as e:
        if e.errno == errno.EXDEV:
            raise CrossDeviceError(
                f"src와 dst가 다른 파일시스템에 있음. "
                f"같은 mount point 하위에 임시 디렉토리를 배치해야 함. "
                f"src={src}, dst={dst}"
            ) from e
        raise AtomicFSError(f"atomic move 실패: {src} -> {dst}: {e}") from e


def ensure_same_filesystem(path_a: PathLike, path_b: PathLike) -> bool:
    """
    두 경로가 같은 파일시스템에 있는지 확인한다.

    임시 디렉토리 생성 전 사전 검증용. 존재하는 가장 가까운 상위 디렉토리의
    st_dev를 비교한다 (경로가 아직 존재하지 않아도 된다).
    """
    def _existing_ancestor(p: Path) -> Path:
        while not p.exists():
            p = p.parent
            if p == p.parent:
                break
        return p

    dev_a = os.stat(str(_existing_ancestor(Path(path_a)))).st_dev
    dev_b = os.stat(str(_existing_ancestor(Path(path_b)))).st_dev
    return dev_a == dev_b
