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
      return Response.redirect("https://github.com/soco-live/animepahe-releases", 302);
    }

    if (path === "/movies") {
      return Response.redirect("https://github.com/soco-live/nkiri-releases", 302);
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
          "version": "1.0.8",
          "build_number": 9,
          "release_notes": "Fixed video playback — anime title and episode now display correctly in Player. Deep link updated to pass full title (anime name + episode + quality).",
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
