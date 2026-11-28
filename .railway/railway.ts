import { defineRailway, github, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "ShowStack";
export default defineRailway(() => {
  const showstackVolume = volume("showstack-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "us-east4-eqdc4a",
    sizeMB: 50000,
  });

  const ShowStack = service("ShowStack", {
    source: github("chazw661/ShowStack", { branch: "main", checkSuites: false, rootDirectory: "/" }),
    build: { builder: "NIXPACKS" },
    start: "python manage.py collectstatic --noinput && python manage.py migrate && python manage.py create_initial_superuser && python manage.py setup_user_groups && python manage.py load_amp_profiles && python manage.py load_cabinets && python manage.py load_drive_capacity && gunicorn audiopatch.wsgi --bind 0.0.0.0:$PORT --workers 3 --timeout 60 --max-requests 1000 --max-requests-jitter 100",
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: { limitOverride: { containers: { cpu: 2, memoryBytes: 2_000_000_000 } } },
    domains: ["showstack.io"],
    networking: { privateNetworkEndpoint: "showstack" },
    volumeMounts: { "/data/media": showstackVolume },
  });

  return project("adequate-truth", {
    variables: { managed: false },
    resources: [ShowStack, showstackVolume],
  });
});
