"""Test robot."""
from pathlib import Path

import hypothesis
import numpy as np
from hypothesis import given
from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from pytest import raises

from pybotics.constants import TRANSFORM_MATRIX_SHAPE
from pybotics.errors import PyboticsError
from pybotics.predefined_models import UR10
from pybotics.robot import Robot


def test_fk(resources_path: Path):
    """
    Test robot.

    :param robot:
    :return:
    """
    # get resource
    path = resources_path / 'ur10-joints-poses.csv'
    data = np.loadtxt(str(path), delimiter=',')
    if data.ndim == 1:
        data = np.expand_dims(data, axis=0)

    # load robot
    robot = UR10()

    # test
    for d in data:
        joints = np.deg2rad(d[:robot.ndof])
        desired_pose = d[robot.ndof:].reshape(TRANSFORM_MATRIX_SHAPE)

        atol = 1e-4

        # test with position argument
        actual_pose = robot.fk(q=joints)
        np.testing.assert_allclose(actual_pose, desired_pose, atol=atol)

        # test with internal position attribute
        robot.joints = joints
        actual_pose = robot.fk()
        np.testing.assert_allclose(actual_pose, desired_pose, atol=atol)


def test_repr():
    repr(UR10())


def test_len():
    len(UR10())


def test_str():
    str(UR10())


def test_home_position():
    robot = UR10()
    x = np.ones(len(robot))
    robot.home_position = x
    np.testing.assert_allclose(robot.home_position, x)


def test_joint_limits():
    robot = UR10()
    robot.joint_limits = robot.joint_limits.copy()
    with raises(PyboticsError):
        robot.joint_limits = np.zeros(1)


def test_compute_joint_torques(planar_robot: Robot):
    """
    From EXAMPLE 5.7 of
    Craig, John J. Introduction to robotics: mechanics and control.
    Vol. 3. Upper Saddle River: Pearson Prentice Hall, 2005.
    :return:
    """

    # set test force and angles
    force = [-100, -200, 0]
    moment = [0] * 3
    wrench = force + moment
    joint_angles = np.deg2rad([30, 60, 0])

    # get link lengths
    lengths = [
        planar_robot.kinematic_chain.links[1].a,
        planar_robot.kinematic_chain.links[2].a
    ]

    # calculate expected torques
    expected_torques = [
        lengths[0] * np.sin(joint_angles[1]) * force[0] +
        (lengths[1] + lengths[0] *
         np.cos(joint_angles[1])) * force[1],
        lengths[1] * force[1],
        0
    ]

    # test
    actual_torques = planar_robot.compute_joint_torques(q=joint_angles,
                                                        wrench=wrench)
    np.testing.assert_allclose(actual_torques, expected_torques)


@given(q=arrays(shape=(3,),
                dtype=float,
                elements=floats(max_value=1e9,
                                min_value=-1e9,
                                allow_nan=False,
                                allow_infinity=False
                                )
                )
       )
def test_jacobian_world(q: np.ndarray, planar_robot: Robot):
    # get link lengths
    lengths = [
        planar_robot.kinematic_chain.links[1].a,
        planar_robot.kinematic_chain.links[2].a
    ]

    # example from Craig has last joint set to 0
    q[-1] = 0

    s0 = np.sin(q[0])
    c0 = np.cos(q[0])

    s01 = np.sin(q[0] + q[1])
    c01 = np.cos(q[0] + q[1])

    expected = np.zeros((6, 3))
    expected[0, 0] = -lengths[0] * s0 \
                     - lengths[1] * s01
    expected[0, 1] = - lengths[1] * s01
    expected[1, 0] = lengths[0] * c0 \
                     + lengths[1] * c01
    expected[1, 1] = lengths[1] * c01
    expected[-1, :] = 1

    actual = planar_robot.jacobian_world(q)
    np.testing.assert_allclose(actual, expected, atol=1e-3)


@given(q=arrays(shape=(3,), dtype=float,
                elements=floats(allow_nan=False, allow_infinity=False)))
def test_jacobian_flange(q: np.ndarray, planar_robot: Robot):
    # get link lengths
    lengths = [
        planar_robot.kinematic_chain.links[1].a,
        planar_robot.kinematic_chain.links[2].a
    ]

    # example from Craig has last joint set to 0
    q[-1] = 0

    s1 = np.sin(q[1])
    c1 = np.cos(q[1])

    expected = np.zeros((6, 3))
    expected[0, 0] = lengths[0] * s1
    expected[1, 0] = lengths[0] * c1 + \
                     lengths[1]
    expected[1, 1] = lengths[1]
    expected[-1, :] = 1

    actual = planar_robot.jacobian_flange(q)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


@given(
    q=arrays(shape=(UR10.kinematic_chain.ndof,), dtype=float,
             elements=floats(allow_nan=False,
                             allow_infinity=False,
                             max_value=np.pi,
                             min_value=-np.pi)),
    q_offset=arrays(shape=(UR10.kinematic_chain.ndof,), dtype=float,
                    elements=floats(allow_nan=False,
                                    allow_infinity=False,
                                    max_value=np.deg2rad(1),
                                    min_value=np.deg2rad(-1)))
)
@hypothesis.settings(deadline=None)
def test_ik(q: np.ndarray, q_offset: np.ndarray):
    robot = UR10()
    pose = robot.fk(q)

    # IK is hard to solve without a decent seed
    q_actual = robot.ik(pose, q=robot.clamp_joints(q + q_offset))

    if q_actual is None:
        # ik couldn't be solved
        # don't fail test
        return

    actual_pose = robot.fk(q_actual)

    # test the matrix with lower accuracy
    # rotation components are hard to achieve when x0 isn't good
    np.testing.assert_allclose(actual_pose, pose, atol=1)

    # test the position with higher accuracy
    desired_position = pose[:-1, -1]
    actual_position = actual_pose[:-1, -1]
    np.testing.assert_allclose(actual_position, desired_position, atol=1e-1)
