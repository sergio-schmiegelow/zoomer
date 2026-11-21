import backend as be
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

PROJECT_FILE = "rot_test.zmr"
PROJECT_INDEX = 0
INTERP_STEPS = 100

project = be.load_project(PROJECT_FILE)

video_size = project["video_data"]["size"]
points0 = project["images_data"][PROJECT_INDEX]["next_points"]
frame0 = project["images_data"][PROJECT_INDEX]["frame"]
points1 = project["images_data"][PROJECT_INDEX + 1]["prev_points"]
frame1 = project["images_data"][PROJECT_INDEX + 1]["frame"]

video_size = np.array(video_size, dtype=np.float32)
points0 = np.array(points0, dtype=np.float32)
frame0 = np.array(frame0, dtype=np.float32)
points1 = np.array(points1, dtype=np.float32)
frame1 = np.array(frame1, dtype=np.float32)

points0 = be.convert_points_and_frame_to_video_coordinates(
    points0, frame0, video_size
)
points1 = be.convert_points_and_frame_to_video_coordinates(
    points1, frame1, video_size
)


ANIMATION = True

steps_list = np.linspace(0, 1, INTERP_STEPS, endpoint=True)


interpolated_points = [
    be._interpolate_points_by_decomposition(
        points0, points1, video_size, alpha
    )
    for alpha in steps_list
]

if ANIMATION:
    fig, ax = plt.subplots()
    scatter = ax.scatter(
        interpolated_points[0][:, 0],
        interpolated_points[0][:, 1],
        c=[(1, 0, 0)],
        label="interpolated points",
    )
    ax.scatter(
        points0[:, 0],
        points0[:, 1],
        c="green",
        marker="o",
        label="points0",
    )
    ax.scatter(
        points1[:, 0],
        points1[:, 1],
        c="black",
        marker="x",
        label="points1",
    )
    ax.legend()

    all_points = np.concatenate([*interpolated_points, points0, points1])
    x_min, y_min = np.min(all_points, axis=0)
    x_max, y_max = np.max(all_points, axis=0)
    x_margin = max((x_max - x_min) * 0.05, 1)
    y_margin = max((y_max - y_min) * 0.05, 1)
    ax.set_xlim(x_min - x_margin, x_max + x_margin)
    ax.set_ylim(y_min - y_margin, y_max + y_margin)

    def update(frame):
        alpha = steps_list[frame]
        scatter.set_offsets(interpolated_points[frame])
        scatter.set_color((1 - alpha, 0, alpha))
        ax.set_title(f"alpha={alpha:.2f}")
        return (scatter,)

    animation = FuncAnimation(
        fig,
        update,
        frames=len(steps_list),
        interval=50,
        blit=False,
    )
    plt.show()
else:
    for alpha, step_points in zip(steps_list, interpolated_points):
        color = (1 - alpha, 0, alpha)
        plt.scatter(
            step_points[:, 0],
            step_points[:, 1],
            c=[color],
            label=f"zoomed alpha={alpha:.2f}",
        )
    plt.show()


quit()
# plot points0 and points1
plt.scatter(points0[:, 0], points0[:, 1], c="r", label="points0")
plt.scatter(points1[:, 0], points1[:, 1], c="b", label="points1")

INTERP_FUNCTION = be._interpolate_points

for alpha in np.linspace(0, 1, INTERP_STEPS):
    interp_points = INTERP_FUNCTION(points0, points1, alpha)
    color = (1 - alpha, 0, alpha)
    plt.scatter(
        interp_points[:, 0],
        interp_points[:, 1],
        c=[color],
        label=f"interp alpha={alpha:.2f}",
    )
plt.show()
