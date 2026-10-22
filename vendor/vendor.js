// CoherentMobiles Vendor Portal Shared Client Utilities

const VendorApp = {
  currentUser: null,
  currentVendor: null,

  async init(activePage, pageTitle, pageSubtitle) {
    const isLoginPage = window.location.pathname.includes("login.html") || window.location.pathname.includes("register.html");
    
    try {
      const res = await fetch("/api/auth/me", { credentials: "include" });
      if (!res.ok) {
        if (!isLoginPage) {
          window.location.href = "/vendor/login.html";
          return;
        }
      } else {
        const data = await res.json();
        if (data.success && data.user) {
          this.currentUser = data.user;
          this.currentVendor = data.vendor;

          if (isLoginPage) {
            window.location.href = "/vendor/dashboard.html";
            return;
          }

          this.renderLayout(activePage, pageTitle, pageSubtitle);
          return true;
        } else if (!isLoginPage) {
          window.location.href = "/vendor/login.html";
          return;
        }
      }
    } catch (err) {
      if (!isLoginPage) {
        window.location.href = "/vendor/login.html";
      }
    }
  },

  renderLayout(activePage, title, subtitle) {
    const sidebarEl = document.getElementById("vendorSidebar");
    if (sidebarEl) {
      sidebarEl.innerHTML = this.getSidebarHTML(activePage);
    }

    const headerEl = document.getElementById("vendorHeader");
    if (headerEl) {
      headerEl.innerHTML = this.getHeaderHTML(title, subtitle);
    }

    // If pending approval, inject prominent banner
    if (this.currentVendor && this.currentVendor.approval_status !== "approved") {
      const contentEl = document.querySelector(".vendor-content");
      if (contentEl) {
        const banner = document.createElement("div");
        banner.className = "alert-banner alert-warning";
        banner.innerHTML = `
          <span style="font-size:24px">⚠️</span>
          <div>
            <strong>Account Pending Admin Approval:</strong>
            Your partner store account is currently in <code>${this.currentVendor.approval_status.toUpperCase()}</code> status.
            You can view your dashboard and orders, but inventory additions and updates will be activated once our partner onboarding team approves your business registration.
          </div>
        `;
        contentEl.insertBefore(banner, contentEl.firstChild);
      }
    }
  },

  getSidebarHTML(activePage) {
    const v = this.currentVendor || {};
    return `
      <div class="sidebar-brand">
        <span class="logo-icon">🏪</span>
        <div>
          <div class="brand-title">CoherentMobiles</div>
          <div style="font-size: 11px; color: #94a3b8;">Partner Vendor Portal</div>
        </div>
        <span class="brand-badge">PRO</span>
      </div>

      <nav class="sidebar-menu">
        <a href="dashboard.html" class="nav-item ${activePage === 'dashboard' ? 'active' : ''}">
          <span class="icon">📊</span> Dashboard
        </a>
        <a href="inventory.html" class="nav-item ${activePage === 'inventory' ? 'active' : ''}">
          <span class="icon">📱</span> Inventory Units
        </a>
        <a href="device-form.html" class="nav-item ${activePage === 'device-form' ? 'active' : ''}">
          <span class="icon">➕</span> Add Device
        </a>
        <a href="bulk-upload.html" class="nav-item ${activePage === 'bulk-upload' ? 'active' : ''}">
          <span class="icon">📁</span> Bulk Upload
        </a>
        <a href="orders.html" class="nav-item ${activePage === 'orders' ? 'active' : ''}">
          <span class="icon">📦</span> Customer Orders
        </a>
        <a href="/index.html" class="nav-item" target="_blank">
          <span class="icon">🌐</span> Public Storefront ↗
        </a>
      </nav>

      <div class="sidebar-footer">
        <div class="vendor-profile-info">
          <span class="vendor-profile-name" title="${v.vendor_name || 'Vendor'}">${v.vendor_name || 'Partner Store'}</span>
          <span class="vendor-profile-code">${v.vendor_code || 'CODE'} • <span style="color:#10b981">${v.approval_status || 'active'}</span></span>
        </div>
        <button class="btn-logout" title="Sign Out" onclick="VendorApp.logout()">🚪</button>
      </div>
    `;
  },

  getHeaderHTML(title, subtitle) {
    const v = this.currentVendor || {};
    const statusClass = v.approval_status === 'approved' ? 'badge-approved' : 'badge-pending';
    return `
      <div class="header-title-box">
        <h1>${title || 'Vendor Portal'}</h1>
        <p>${subtitle || 'Manage your certified refurbished inventory and orders'}</p>
      </div>
      <div class="header-actions">
        <span class="badge ${statusClass}">
          ● ${v.approval_status ? v.approval_status.toUpperCase() : 'PENDING'}
        </span>
        <a href="device-form.html" class="btn btn-primary btn-sm">
          <span>➕</span> Add Unit
        </a>
      </div>
    `;
  },

  async logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch (e) {}
    window.location.href = "/vendor/login.html";
  },

  showToast(message, isSuccess = true) {
    let toast = document.getElementById("cmToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "cmToast";
      toast.className = "cm-toast";
      document.body.appendChild(toast);
    }
    toast.className = `cm-toast ${isSuccess ? 'success' : 'error'}`;
    toast.textContent = message;
    toast.style.display = "block";
    setTimeout(() => {
      toast.style.display = "none";
    }, 4000);
  },

  formatINR(val) {
    if (val === null || val === undefined || isNaN(val)) return "₹0";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(val);
  },

  formatDate(dateStr) {
    if (!dateStr) return "-";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
      });
    } catch (e) {
      return dateStr;
    }
  },

  validateLuhn(imei) {
    if (!imei || typeof imei !== "string") return false;
    const clean = imei.trim();
    if (clean.length !== 15 || !/^\d+$/.test(clean)) return false;
    const digits = clean.split("").map(Number);
    let sum = 0;
    for (let i = 0; i < digits.length; i++) {
      let d = digits[i];
      if (i % 2 === 1) {
        d *= 2;
        if (d > 9) d -= 9;
      }
      sum += d;
    }
    return sum % 10 === 0;
  }
};
