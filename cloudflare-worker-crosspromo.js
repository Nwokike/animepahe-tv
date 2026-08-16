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
    //    ┌─────────────────────────────────────────────────────────────┐
    //    │  CROSS-PROMO COPY — deploy for ~24h, then swap back to     │
    //    │  cloudflare-worker.js.                                     │
    //    │                                                             │
    //    │  animepahe  : UNCHANGED (real update, build 9 > client 8)  │
    //    │  nkiri      : BUMPED 1→2, update_url → anime page          │
    //    │  socolive   : BUMPED 1→2, update_url → anime page          │
    //    └─────────────────────────────────────────────────────────────┘
    if (path === "/config") {
      const configData = {
        "socolive": {
          "version": "1.0.0",
          "build_number": 2,
          "release_notes": "AnimePahe TV is back and fully working again — video playback, titles, and episodes have been fixed. Heads up: AnimePahe TV opens video in KTV Player, so make sure your KTV Player is updated to the latest version (grab it from the Play Store or wherever you got it). If you use any other player for anime, update that too. Then download the latest AnimePahe TV to get started.",
          "mandatory": false,
          "update_url": `${origin}/anime`
        },
        "animepahe": {
          "version": "1.0.8",
          "build_number": 9,
          "release_notes": "Fixed video playback — anime title and episode now display correctly in KTV Player. Deep link updated to pass full title (anime name + episode + quality).",
          "mandatory": false,
          "update_url": `${origin}/anime`
        },
        "nkiri": {
          "version": "1.0.0",
          "build_number": 2,
          "release_notes": "AnimePahe TV is back and fully working again — video playback, titles, and episodes have been fixed. Make sure your KTV Player is updated to the latest version (grab it from the Play Store or wherever you got it). If you use any other player for anime, update that too. Then download the latest AnimePahe TV to get started.",
          "mandatory": false,
          "update_url": `${origin}/anime`
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
