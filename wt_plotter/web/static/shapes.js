// 通用几何形状：只建立路径，填充和描边由调用方决定。
// size 是外接正方形边长，angle 为弧度（0 指向 +x，仅箭头使用）。

// 以 (x, y) 为中心、按 angle 旋转后连成闭合多边形。
function polygon(ctx, vertices, x, y, angle) {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    vertices.forEach(([vx, vy], i) => {
        const px = x + vx * cos - vy * sin;
        const py = y + vx * sin + vy * cos;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    });
    ctx.closePath();
}

function regular(sides, radius) {
    return Array.from({ length: sides }, (_, i) => {
        const a = -Math.PI / 2 + i * 2 * Math.PI / sides;
        return [radius * Math.cos(a), radius * Math.sin(a)];
    });
}

function path(ctx, shape, x, y, size, angle = 0) {
    const h = size / 2;
    ctx.beginPath();
    switch (shape) {
        case 'circle':
            ctx.arc(x, y, h, 0, Math.PI * 2);
            break;
        case 'square':
            ctx.rect(x - h, y - h, size, size);
            break;
        case 'diamond':
            polygon(ctx, [[0, -h], [h, 0], [0, h], [-h, 0]], x, y, 0);
            break;
        case 'triangle':
            polygon(ctx, [[0, -h], [h, h], [-h, h]], x, y, 0);
            break;
        case 'pentagon':
            polygon(ctx, regular(5, h), x, y, 0);
            break;
        case 'circle-cross':
            ctx.arc(x, y, h, 0, Math.PI * 2);
            ctx.moveTo(x - h, y);
            ctx.lineTo(x + h, y);
            ctx.moveTo(x, y - h);
            ctx.lineTo(x, y + h);
            break;
        case 'arrow':
            polygon(ctx, [[h, 0], [-h, h * 0.8], [-h * 0.4, 0], [-h, -h * 0.8]], x, y, angle);
            break;
        default:
            throw new Error(`Unknown shape: ${shape}`);
    }
}

window.Shapes = { path };
