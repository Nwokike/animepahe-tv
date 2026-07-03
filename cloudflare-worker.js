export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const origin = url.origin;

    // 1. THE DYNAMIC REDIRECTS (Banners & Update Links)
    if (path === "/sports" || path === "/football") {
      return Response.redirect("https://soco-live.github.io", 302);
    }

    if (path === "/anime") {
      return Response.redirect("https://animepahetv.github.io", 302);
    }

    if (path === "/movies") {
      return Response.redirect("https://nkiritv.github.io", 302);
    }

    // 2. THE BACKGROUND UPDATE CHECK (Flet app calls this silently)
    if (path === "/config") {
      const configData = {
        "socolive": {
          "version": "1.0.0",
          "build_number": 1,
          "release_notes": "Live feed buffer optimizations and stream layout enhancements.",
          "mandatory": false,
          "update_url": `${origin}/sports`
        },
        "animepahe": {
          "version": "1.0.7",
          "build_number": 8,
          "release_notes": "Migrated HTTP client from httpx to primp for Cloudflare TLS fingerprint compatibility on Linux. Replaced httpx dependency with primp ; added PyQt6-WebEngine + qtpy as dev dependencies for desktop CAPTCHA solver.",
          "mandatory": false,
          "update_url": `${origin}/anime`
        },
        "nkiri": {
          "version": "1.0.0",
          "build_number": 1,
          "release_notes": "Cinematic media resolution upgrades and backend scraper enhancements.",
          "mandatory": false,
          "update_url": `${origin}/movies`
        }
      };

      return new Response(JSON.stringify(configData), {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*"
        }
      });
    }

    // 3. FALLBACK FOR SNOOPERS
    return new Response("404 Not Found", { status: 404 });
  }
};
