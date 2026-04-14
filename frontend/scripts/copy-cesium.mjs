import fs from 'fs';
import path from 'path';

const src = path.join(process.cwd(), 'node_modules', 'cesium', 'Build', 'Cesium');
const dest = path.join(process.cwd(), 'public', 'Cesium');

if (!fs.existsSync(dest)) {
  console.log('Copying Cesium assets to public/Cesium...');
  fs.cpSync(src, dest, { recursive: true });
  console.log('Cesium assets copied successfully!');
} else {
  console.log('Cesium assets already exist in public/Cesium, skipping.');
}
