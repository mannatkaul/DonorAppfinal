import "./index.css";

declare global {
  interface Window {
    __DONOR_API_BASE_URL__?: string;
  }
}

window.__DONOR_API_BASE_URL__ = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8001"
).replace(/\/$/, "");

const assetRoot = `${import.meta.env.BASE_URL}assets/`;

const stylesheet = document.createElement("link");
stylesheet.rel = "stylesheet";
stylesheet.href = `${assetRoot}index-BV8vfNig.css`;
document.head.append(stylesheet);

const application = document.createElement("script");
application.type = "module";
application.src = `${assetRoot}index-D2QvHT6c.js`;
application.onerror = () => {
  throw new Error("Could not load the restored donor portal application bundle.");
};
document.body.append(application);
