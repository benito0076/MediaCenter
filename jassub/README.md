JASSUB 2.5.38 (https://github.com/ThaUnknown/jassub), licence : voir LICENSE.
Assemblé depuis le paquet npm (build SIMD « modern » uniquement) :

    npm i jassub@2.5.38 esbuild
    npx esbuild node_modules/jassub/dist/jassub.js --bundle --format=esm --minify --outfile=jassub.js
    npx esbuild node_modules/jassub/dist/worker/worker.js --bundle --format=esm --minify --outfile=worker/worker.js
    cp node_modules/jassub/dist/wasm/jassub-worker-modern.{js,wasm} wasm/
    cp node_modules/jassub/dist/default.woff2 node_modules/jassub/LICENSE .
