const fs = require('fs');

async function fetchArtifact(core, github, repo) {
  const artifacts = await github.rest.actions.listArtifactsForRepo({
    owner: repo.owner,
    repo: repo.repo,
  });
  const filteredArtifacts = artifacts.data.artifacts.filter(artifact => artifact.name === process.env.ARTIFACT_NAME);
  let latestArtifact = null;

  for (const artifact of filteredArtifacts) {
    const run = await github.rest.actions.getWorkflowRun({
      owner: repo.owner,
      repo: repo.repo,
      run_id: artifact.workflow_run.id,
    });

    if (run.data.head_branch === process.env.BRANCH_NAME) {
      if (!latestArtifact || new Date(artifact.created_at) > new Date(latestArtifact.created_at)) {
        latestArtifact = artifact;
      }
    }
  }

  if (latestArtifact) {
    console.log(`Found latest artifact: ${latestArtifact.id}`);
    core.setOutput('artifact_id', latestArtifact.id.toString());
    return { artifactId: latestArtifact.id.toString()};
  } else {
    console.log('No matching artifacts found.');
    core.setOutput('artifact_id', '');
    return { artifactId: '' };
  }
}

async function downloadArtifact(github, repo, artifactId) {
  const benchmarksDir = process.env.BENCHMARKS_DIR;
  const artifactPath = process.env.ARTIFACT_PATH;

  const download = await github.rest.actions.downloadArtifact({
    owner: repo.owner,
    repo: repo.repo,
    artifact_id: artifactId,
    archive_format: 'zip',
  });

  if (!fs.existsSync(benchmarksDir)) {
    fs.mkdirSync(benchmarksDir, { recursive: true });
  }
  fs.writeFileSync(artifactPath, Buffer.from(download.data));
  console.log('Artifact downloaded:', artifactPath);
}

module.exports = {
    fetchArtifact,
    downloadArtifact
};
