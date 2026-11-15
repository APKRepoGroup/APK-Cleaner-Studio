// Generate the checked-in web and native AC icons from the approved vector geometry.
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require('sharp');

const root = path.resolve(__dirname, '..');
const smallSizes = [16, 20, 24, 32];

const sizes = [16, 20, 24, 32, 48, 64, 128, 256];
const ink = '#050908', lime = '#D9FF43', mint = '#48D5A8';
// Outlines of the existing Arial Bold AC, not a replacement typeface.
const a = 'M136.47 0H106.597L94.722 -30.894H40.356L29.131 0H0L52.974 -136.006H82.012Z M85.908 -53.809L67.168 -104.277L48.799 -53.809Z';
const c = 'M100.845 -50.005L127.471 -41.563C123.389 -26.719 116.601 -15.694 107.107 -8.489C97.613 -1.283 85.568 2.319 70.972 2.319C52.912 2.319 38.068 -3.85 26.44 -16.189C14.813 -28.528 8.999 -45.397 8.999 -66.797C8.999 -89.434 14.844 -107.014 26.533 -119.539C38.223 -132.063 53.592 -138.325 72.642 -138.325C89.279 -138.325 102.793 -133.408 113.184 -123.574C119.368 -117.76 124.007 -109.411 127.1 -98.525L99.917 -92.031C98.309 -99.082 94.954 -104.648 89.851 -108.73C84.749 -112.813 78.548 -114.854 71.25 -114.854C61.169 -114.854 52.989 -111.235 46.711 -103.999C40.434 -96.763 37.295 -85.042 37.295 -68.838C37.295 -51.644 40.387 -39.398 46.572 -32.1C52.757 -24.801 60.798 -21.152 70.693 -21.152C77.992 -21.152 84.269 -23.472 89.526 -28.11C94.784 -32.749 98.556 -40.047 100.845 -50.005Z';

function icon(size) {
  // Give AC more breathing room without changing the tile or the mint bar.
  // Keep the bar on full pixels at the smallest sizes.
  const tiny = {
    16: { width: 9.85, height: 5.6, baseline: 10.55, bar: 6, y: 12, h: 1, stroke: 6.5 },
    20: { width: 11.7, height: 6.75, baseline: 12.73, bar: 8, y: 15, h: 1, stroke: 5 },
    24: { width: 13.8, height: 8.1, baseline: 15.35, bar: 10, y: 18, h: 1.5, stroke: 3.7 },
    32: { width: 17.3, height: 10.1, baseline: 20.25, bar: 12, y: 24, h: 2, stroke: 2.8 },
  }[size];
  const view = tiny ? size : 512;
  const unit = view / 512;
  const rectangle = (x, y, w, h, rx, style) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" ${style}/>`;
  const advance = 136.2, glyphWidth = advance + 127.471;
  const width = tiny?.width ?? glyphWidth + 1.6;
  const xScale = width / glyphWidth;
  const yScale = tiny ? tiny.height / 140.644 : 1;
  const baseline = tiny?.baseline ?? 324;
  const stroke = tiny?.stroke ?? 1.6;
  const barWidth = tiny?.bar ?? 160;
  const barHeight = tiny?.h ?? 16;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${view} ${view}" role="img" aria-label="APK Cleaner Studio AC">
${rectangle(24*unit, 24*unit, 464*unit, 464*unit, 136*unit, `fill="${ink}"`)}
${size <= 20 ? '' : rectangle(49*unit, 49*unit, 414*unit, 414*unit, 115*unit, `fill="none" stroke="#15201C" stroke-width="${tiny ? 0.018 * view : 4.2}"`)}
<g transform="translate(${(view - width) / 2} ${baseline}) scale(${xScale} ${yScale})" fill="${lime}" stroke="${lime}" stroke-width="${stroke}" stroke-linejoin="round"><path d="${a}"/><path d="${c}" transform="translate(${advance} 0)"/></g>
${rectangle((view-barWidth)/2, tiny?.y ?? 392, barWidth, barHeight, barHeight/2, `fill="${mint}"`)}
</svg>`;
}

function androidVector(svg) {
  // The vector master contains only these rectangles and translated paths.
  const attributes = tag => Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [key, value]));
  const roundRect = (x, y, w, h, r) => `M${x+r},${y} H${x+w-r} A${r},${r} 0 0 1 ${x+w},${y+r} V${y+h-r} A${r},${r} 0 0 1 ${x+w-r},${y+h} H${x+r} A${r},${r} 0 0 1 ${x},${y+h-r} V${y+r} A${r},${r} 0 0 1 ${x+r},${y} Z`;
  const paint = attrs => `${attrs.fill && attrs.fill !== 'none' ? ` android:fillColor="${attrs.fill}"` : ''}${attrs.stroke ? ` android:strokeColor="${attrs.stroke}" android:strokeWidth="${attrs['stroke-width']}" android:strokeLineJoin="round"` : ''}`;
  const shapes = [...svg.matchAll(/<rect [^>]+\/>/g)].map(([tag]) => {
    const attrs = attributes(tag);
    const d = roundRect(...['x', 'y', 'width', 'height', 'rx'].map(key => Number(attrs[key])));
    return `    <path${paint(attrs)} android:pathData="${d}" />`;
  });
  const [_, groupTag, content] = svg.match(/(<g [^>]+>)(.*?)<\/g>/s);
  const group = attributes(groupTag);
  const [, tx, ty, sx, sy] = group.transform.match(/^translate\(([^ ]+) ([^)]+)\) scale\(([^ ]+) ([^)]+)\)$/);
  const letters = [...content.matchAll(/<path [^>]+\/>/g)].map(([tag]) => {
    const attrs = attributes(tag);
    const letter = `<path${paint(group)} android:pathData="${attrs.d}" />`;
    const shift = attrs.transform?.match(/^translate\(([^ ]+) 0\)$/)?.[1];
    return shift ? `        <group android:translateX="${shift}">\n            ${letter}\n        </group>` : `        ${letter}`;
  });
  return `<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="48dp" android:height="48dp" android:viewportWidth="512" android:viewportHeight="512">\n${shapes.slice(0, 2).join('\n')}\n    <group android:translateX="${tx}" android:translateY="${ty}" android:scaleX="${sx}" android:scaleY="${sy}">\n${letters.join('\n')}\n    </group>\n${shapes[2]}\n</vector>\n`;
}

function writeIco(frames) {
  const header = Buffer.alloc(6 + frames.size * 16);
  header.writeUInt16LE(1, 2); header.writeUInt16LE(frames.size, 4);
  let offset = header.length, index = 6;
  for (const [size, png] of frames) {
    header[index] = header[index + 1] = size % 256;
    header.writeUInt16LE(1, index + 4); header.writeUInt16LE(32, index + 6);
    header.writeUInt32LE(png.length, index + 8); header.writeUInt32LE(offset, index + 12);
    offset += png.length; index += 16;
  }
  return Buffer.concat([header, ...frames.values()]);
}

async function main() {
  const master = icon(512);
  const render = svg => sharp(Buffer.from(svg)).png().toBuffer();
  const frames = new Map(await Promise.all(sizes.map(async size => [size, await render(icon(size))])));
  const common = {
    'favicon.svg': master + '\n',
    'favicon.png': await render(master),
    'favicon.ico': writeIco(frames),
    ...Object.fromEntries(smallSizes.map(size => [`favicon-${size}.svg`, icon(size) + '\n'])),
  };
  for (const folder of ['public', 'studio/web']) {
    await Promise.all(Object.entries(common).map(([name, data]) => fs.writeFile(path.join(root, folder, name), data)));
  }
  const vectorDir = path.join(root, 'android/app/src/main/res/mipmap-anydpi');
  await fs.mkdir(vectorDir, { recursive: true });
  await fs.writeFile(path.join(vectorDir, 'ic_launcher.xml'), androidVector(master));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
