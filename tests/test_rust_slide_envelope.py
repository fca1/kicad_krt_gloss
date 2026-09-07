import math
import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
import grid_router
from dgloss.krt_api import Segment, _segment_fits_wide
from routing_config import GridCoord
from dgloss.segment_sliding import _ordered_geometry, _joints_at_offset
from tools.rust_slide_envelope import envelope, GridProbe
from test_adaptive_segment_slide import fixture


@pytest.mark.parametrize('turns',range(8))
@pytest.mark.parametrize('reflect',[False,True])
def test_centered_envelope_covers_moving_endpoints(turns,reflect):
    ctx,source,_=fixture(turns,reflect)
    geometry=_ordered_geometry(*source)
    sign=-1 if reflect else 1
    centered=envelope(geometry,source[1],0,1,sign)
    initial=envelope(geometry,source[1],0,1,sign,False)
    assert centered.width-source[1].width == pytest.approx((initial.width-source[1].width)/2)
    from dgloss.krt_api import point_to_segment_distance
    for t in (0,.25,.5,.75,1):
        for point in _joints_at_offset(geometry,sign*t):
            distance=point_to_segment_distance(*point,centered.start_x,centered.start_y,centered.end_x,centered.end_y)
            assert distance <= (centered.width-source[1].width)/2+1e-8
    # Native grid/margin path is callable for all orientations and cached.
    probe=GridProbe(ctx,1)
    result=probe.clears(centered)
    assert probe.clears(centered)==result
    assert probe.calls==1 and probe.hits==1


def test_zero_margin_raw_rust_only_checks_endpoint_but_krt_wrapper_covers_line():
    obstacles=grid_router.GridObstacleMap(1)
    obstacles.add_blocked_cell(5,0,0)
    assert not obstacles.segment_blocked(0,0,10,0,0,0.)
    segment=Segment(0,0,1,0,.3,'F.Cu',1)
    assert not _segment_fits_wide(segment,obstacles,GridCoord(.1),0,0.)


def test_point_three_mm_is_three_cells_of_radius_at_point_one_grid():
    obstacles=grid_router.GridObstacleMap(1)
    obstacles.add_blocked_cell(5,3,0)
    radius=.3/.1
    assert obstacles.segment_blocked(0,0,10,0,0,round(radius,12))
    assert not obstacles.segment_blocked(0,0,10,0,0,2.9)
    assert 2*.3 == pytest.approx(.6)  # Corresponding added physical width.
