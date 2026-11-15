// 把逐帧的无编号点串成轨迹，按最近距离贪心配对。
// frames 按 t 升序（毫秒）。可接续的距离 = jitter + maxSpeed × 间隔秒数，
// maxGap 限制中断时长。
function linkTracks(frames, { maxSpeed, jitter, maxGap }) {
    const tracks = [];
    let open = [];
    for (const frame of frames) {
        open = open.filter(track => frame.t - track.lastT <= maxGap);
        const pairs = [];
        frame.points.forEach((point, pi) => {
            open.forEach((track, ti) => {
                const last = track.points[track.points.length - 1];
                const d = Math.hypot(point.x - last.x, point.y - last.y);
                if (d <= jitter + maxSpeed * (frame.t - track.lastT) / 1000) pairs.push([d, ti, pi]);
            });
        });
        pairs.sort((a, b) => a[0] - b[0]);
        const usedTracks = new Set();
        const usedPoints = new Set();
        for (const [, ti, pi] of pairs) {
            if (usedTracks.has(ti) || usedPoints.has(pi)) continue;
            usedTracks.add(ti);
            usedPoints.add(pi);
            open[ti].points.push({ ...frame.points[pi], t: frame.t });
            open[ti].lastT = frame.t;
        }
        frame.points.forEach((point, pi) => {
            if (usedPoints.has(pi)) return;
            const track = { points: [{ ...point, t: frame.t }], lastT: frame.t };
            tracks.push(track);
            open.push(track);
        });
    }
    return tracks.map(track => track.points);
}

// 按距离合并相近的点，每组保留 pick 选中的点。
function clusterPoints(points, radius, pick) {
    const groups = [];
    for (const point of points) {
        const group = groups.find(g => Math.hypot(g[0].x - point.x, g[0].y - point.y) <= radius);
        if (group) group.push(point);
        else groups.push([point]);
    }
    return groups.map(pick);
}

// 查找最后一个 key(item) <= value 的下标。
function lastIndexAtMost(items, value, key) {
    let lo = 0;
    let hi = items.length - 1;
    let found = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (key(items[mid]) <= value) {
            found = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return found;
}

window.Tracks = { linkTracks, clusterPoints, lastIndexAtMost };
