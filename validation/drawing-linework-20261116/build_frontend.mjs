import {build} from 'file:///C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend/node_modules/vite/dist/node/index.js';

// Reuse the identical package-lock dependency installation read-only.
// This configuration is only for the isolated local build, not application code.
await build({
  root:'D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115/frontend',
  resolve:{alias:[
    {find:/^three$/,replacement:'C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend/node_modules/three/build/three.module.js'},
    {find:/^three\/addons\//,replacement:'C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend/node_modules/three/examples/jsm/'},
  ]},
  build:{outDir:'D:/稀土agent-稀土制暖全流程/outputs/drawing-linework-20261116/frontend-dist',emptyOutDir:false},
});
