import math
import pytest
from tools.prototype_collinear_supports import solve_supports


@pytest.mark.parametrize('angle', [0,45,90,135,180,225,270,315])
def test_already_centered_straight_support(angle):
    def rotate(p):
        c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        return p[0]*c-p[1]*s,p[0]*s+p[1]*c
    points=list(map(rotate,[(0,0),(10,0),(20,0)]))
    result=solve_supports(points,[(0,rotate((6,0))),(1,rotate((14,0)))])
    assert result is not None
    assert all(math.dist(a,b)<1e-7 for a,b in zip(points,result))


def test_shared_translation_keeps_internal_joint():
    points=[(0,0),(2,2),(5,2),(8,2),(10,0)]
    result=solve_supports(points,[(1,(3,3)),(2,(7,3))])
    assert result==[(0,0),(3.,3.),(5.,3.),(7.,3.),(10,0)]


def test_reversing_traversal_keeps_same_solution():
    points=[(0,0),(2,2),(5,2),(8,2),(10,0)]
    expected=solve_supports(points,[(1,(3,3)),(2,(7,3))])
    result=solve_supports(list(reversed(points)),[(2,(3,3)),(1,(7,3))])
    assert result==list(reversed(expected))


def test_one_constraint_moves_the_whole_common_support():
    assert solve_supports([(0,0),(2,2),(5,2),(8,2),(10,0)],[(1,(3,3))]) == [
        (0,0),(3.,3.),(5.,3.),(7.,3.),(10,0)]


def test_contradictory_gates_rejected():
    assert solve_supports([(0,0),(2,2),(5,2),(8,2),(10,0)],
                          [(1,(3,3)),(2,(7,4))]) is None


def test_anchors_and_reversals_not_relaxed():
    assert solve_supports([(0,0),(5,0),(10,0)],[(0,(3,1))]) is None
    assert solve_supports([(0,0),(5,0),(2,0)],[]) is None
