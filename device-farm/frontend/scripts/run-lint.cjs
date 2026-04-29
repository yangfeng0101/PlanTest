const { spawnSync } = require('node:child_process')
const path = require('node:path')

const eslintArgs = [
  'src',
  'vite.config.ts',
  '--ext',
  'ts,tsx',
  '--report-unused-disable-directives',
  '--max-warnings',
  '0',
]

const nodeMajor = Number(process.versions.node.split('.')[0])
const supportsLocalEslint = nodeMajor >= 20 && nodeMajor < 23

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    ...options,
  })

  if (result.error) {
    return { status: 1, error: result.error }
  }
  return { status: result.status ?? 1 }
}

if (supportsLocalEslint) {
  const eslintBin = path.join(__dirname, '..', 'node_modules', 'eslint', 'bin', 'eslint.js')
  process.exit(run(process.execPath, [eslintBin, ...eslintArgs]).status)
}

const dockerCheck = run('docker', ['--version'], { stdio: 'ignore' })
if (dockerCheck.status !== 0) {
  console.error(
    `Node ${process.versions.node} is outside this project's supported lint range. ` +
      'Use Node 20-22, or install Docker so npm run lint can use node:20-alpine.'
  )
  process.exit(1)
}

const dockerArgs = [
  'run',
  '--rm',
  '-v',
  `${path.resolve(__dirname, '..')}:/app`,
  '-w',
  '/app',
  'node:20-alpine',
  'npm',
  'run',
  'lint:local',
]

process.exit(run('docker', dockerArgs).status)
