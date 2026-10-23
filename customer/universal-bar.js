// CoherentMobiles Universal Single-Localhost Role Switcher & Navigation Bar
// Enables seamless pair testing between Customer Storefront, K.T. Street Stores Map, Vendor Portal, and Admin Portal.

(function() {
  function injectStyles() {
    if (document.getElementById("cmUniversalTopBarStyles")) return;
    const style = document.createElement("style");
    style.id = "cmUniversalTopBarStyles";
    style.textContent = `
      .cm-universal-top-bar {
        background: #0f172a;
        color: #f8fafc;
        padding: 8px 16px;
        font-size: 12px;
        border-bottom: 1px solid #334155;
        position: sticky;
        top: 0;
        z-index: 99999;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      }
      .cm-top-bar-inner {
        max-width: 1400px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
      }
      .cm-top-brand {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 800;
        letter-spacing: 0.3px;
        color: #f8fafc;
      }
      .cm-live-dot {
        color: #10b981;
        font-size: 14px;
        animation: cmPulse 2s infinite;
      }
      .cm-top-tag {
        background: #1e293b;
        color: #94a3b8;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        border: 1px solid #334155;
      }
      .cm-top-nav {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .cm-top-btn {
        color: #cbd5e1;
        text-decoration: none;
        padding: 5px 12px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 12px;
        transition: all 0.15s;
        background: transparent;
        border: 1px solid transparent;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .cm-top-btn:hover {
        background: #1e293b;
        color: #ffffff;
        border-color: #475569;
      }
      .cm-top-btn.active {
        background: #d6336c;
        color: #ffffff;
        border-color: #d6336c;
        box-shadow: 0 2px 8px rgba(214, 51, 108, 0.4);
      }
      .cm-role-selector {
        background: #1e293b;
        color: #f1f5f9;
        border: 1.5px solid #475569;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 11.5px;
        font-weight: 700;
        outline: none;
        cursor: pointer;
      }
      .cm-role-selector:focus {
        border-color: #d6336c;
      }
      @keyframes cmPulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.4; transform: scale(0.9); }
      }
    `;
    document.head.appendChild(style);
  }

  function renderUniversalTopBar() {
    if (document.getElementById("cmUniversalTopBar")) return;
    injectStyles();

    const path = window.location.pathname.toLowerCase();
    let currentMode = 'customer';
    if (path.includes('stores')) currentMode = 'stores';
    else if (path.includes('vendor')) currentMode = 'vendor';
    else if (path.includes('crud-dashboard') || path.includes('admin')) currentMode = 'admin';

    const bar = document.createElement("div");
    bar.id = "cmUniversalTopBar";
    bar.className = "cm-universal-top-bar";
    bar.innerHTML = `
      <div class="cm-top-bar-inner">
        <div class="cm-top-brand">
          <span class="cm-live-dot">●</span>
          <strong>CoherentMobiles</strong>
          <span class="cm-top-tag">Mysuru K.T. Street Localhost</span>
        </div>
        <div class="cm-top-nav">
          <a href="/" class="cm-top-btn ${currentMode === 'customer' ? 'active' : ''}">🛍️ Customer Store</a>
          <a href="/stores.html" class="cm-top-btn ${currentMode === 'stores' ? 'active' : ''}">📍 K.T. Street Stores</a>
          <a href="/vendor/dashboard.html" class="cm-top-btn ${currentMode === 'vendor' ? 'active' : ''}">🏪 Vendor Portal</a>
          <a href="/crud-dashboard.html" class="cm-top-btn ${currentMode === 'admin' ? 'active' : ''}">⚙️ Admin Portal</a>
        </div>
        <div class="cm-top-demo">
          <select id="cmRoleSelector" onchange="handleUniversalRoleSwitch(this.value)" class="cm-role-selector">
            <option value="">⚡ 1-Click Role Switcher...</option>
            <option value="customer">🛍️ Customer View (Storefront)</option>
            <option value="vendor_ist">🏪 Vendor: Chamundi Galleria (IST-IND)</option>
            <option value="vendor_apx">🏪 Vendor: Cauvery Junction (APX-DST)</option>
            <option value="vendor_krs">🏪 Vendor: K.T. Refurb Studio (KRS-KTS)</option>
            <option value="admin">⚙️ Admin: System Administrator</option>
          </select>
        </div>
      </div>
    `;

    document.body.insertBefore(bar, document.body.firstChild);
  }

  window.handleUniversalRoleSwitch = async function(targetRole) {
    if (!targetRole) return;
    
    if (targetRole === 'customer') {
      window.location.href = '/';
      return;
    }
    
    let loginPayload = {};
    let redirectUrl = '/vendor/dashboard.html';
    
    if (targetRole === 'vendor_ist') {
      loginPayload = { login: 'IST-IND', password: 'Vendor@123' };
    } else if (targetRole === 'vendor_apx') {
      loginPayload = { login: 'APX-DST', password: 'Vendor@123' };
    } else if (targetRole === 'vendor_krs') {
      loginPayload = { login: 'KRS-KTS', password: 'Vendor@123' };
    } else if (targetRole === 'admin') {
      loginPayload = { login: 'admin@coherent.test', password: 'Admin@123' };
      redirectUrl = '/crud-dashboard.html';
    }
    
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(loginPayload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        if (data.token) {
          localStorage.setItem('cm_vendor_token', data.token);
        }
        window.location.href = redirectUrl;
      } else {
        alert("Role switch error: " + (data.error || "Please login manually"));
      }
    } catch (e) {
      alert("Network error switching role: " + e.message);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderUniversalTopBar);
  } else {
    renderUniversalTopBar();
  }
})();
