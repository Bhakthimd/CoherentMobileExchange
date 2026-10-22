// CoherentMobiles Admin Management Controller
// Connects /admin to /api/admin/* endpoints with authentication guard and vendor approval management

(function() {
  'use strict';

  let currentAdminUser = null;

  async function checkAdminAuth() {
    try {
      const res = await fetch("/api/auth/me", { credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.user && data.user.role === "admin") {
          currentAdminUser = data.user;
          injectAdminControls();
          return;
        }
      }
    } catch (e) {}

    showAdminLoginModal();
  }

  function showAdminLoginModal() {
    let modal = document.getElementById("adminAuthModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "adminAuthModal";
      modal.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,23,42,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;padding:20px;";
      modal.innerHTML = `
        <div style="background:#fff;border-radius:16px;width:100%;max-width:420px;padding:32px;box-shadow:0 20px 40px rgba(0,0,0,0.4);font-family:inherit;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
            <span style="font-size:28px;">⚙️</span>
            <div>
              <h2 style="font-size:18px;font-weight:800;color:#0f172a;margin:0;">Administrator Portal</h2>
              <p style="font-size:12px;color:#64748b;margin:0;">Authentication required to manage vendors & catalog</p>
            </div>
          </div>
          <div id="adminLoginErr" style="display:none;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;padding:10px;border-radius:8px;font-size:12px;margin-bottom:14px;"></div>
          <form id="adminLoginForm" onsubmit="handleAdminLogin(event)">
            <div style="margin-bottom:14px;">
              <label style="display:block;font-size:12px;font-weight:700;color:#334155;margin-bottom:4px;">Admin Email</label>
              <input type="email" id="adminEmailInput" value="admin@coherent.test" style="width:100%;padding:10px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13.5px;" required>
            </div>
            <div style="margin-bottom:20px;">
              <label style="display:block;font-size:12px;font-weight:700;color:#334155;margin-bottom:4px;">Password</label>
              <input type="password" id="adminPwdInput" value="Admin@123" style="width:100%;padding:10px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13.5px;" required>
            </div>
            <button type="submit" id="adminLoginBtn" style="width:100%;padding:11px;background:#d6336c;color:#fff;border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:14px;">
              Authenticate as Admin
            </button>
          </form>
          <div style="margin-top:16px;text-align:center;">
            <a href="/index.html" style="font-size:12.5px;color:#64748b;text-decoration:none;">← Return to Storefront</a>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = "flex";
  }

  window.handleAdminLogin = async function(e) {
    e.preventDefault();
    const email = document.getElementById("adminEmailInput").value.trim();
    const password = document.getElementById("adminPwdInput").value;
    const errBox = document.getElementById("adminLoginErr");
    const btn = document.getElementById("adminLoginBtn");

    errBox.style.display = "none";
    btn.disabled = true;
    btn.textContent = "Authenticating...";

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ login: email, password: password })
      });
      const data = await res.json();
      if (res.ok && data.success && data.user && data.user.role === "admin") {
        document.getElementById("adminAuthModal").style.display = "none";
        currentAdminUser = data.user;
        injectAdminControls();
        location.reload();
      } else {
        errBox.textContent = data.error || "Access denied: Account is not an administrator.";
        errBox.style.display = "block";
      }
    } catch (err) {
      errBox.textContent = "Network error connecting to auth service.";
      errBox.style.display = "block";
    } finally {
      btn.disabled = false;
      btn.textContent = "Authenticate as Admin";
    }
  };

  async function injectAdminControls() {
    // Enhance Vendor management section with approval controls
    const vendorGrid = document.querySelector(".vendor-cards-grid") || document.getElementById("vendorsSection");
    if (!vendorGrid) return;

    try {
      const res = await fetch("/api/admin/vendors", { credentials: "include" });
      if (!res.ok) return;
      const data = await res.json();
      const vendors = data.vendors || [];

      // Create an admin vendor approvals bar
      let approvalsBar = document.getElementById("adminApprovalsBar");
      if (!approvalsBar) {
        approvalsBar = document.createElement("div");
        approvalsBar.id = "adminApprovalsBar";
        approvalsBar.style.cssText = "background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.05);";
        vendorGrid.parentNode.insertBefore(approvalsBar, vendorGrid);
      }

      approvalsBar.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
          <div>
            <h3 style="font-size:16px;font-weight:800;color:#0f172a;margin:0;">Vendor Partner Approvals</h3>
            <p style="font-size:12px;color:#64748b;margin:0;">Review pending onboarding registrations and manage partner access</p>
          </div>
          <span style="font-size:12px;font-weight:700;padding:4px 10px;background:#f1f5f9;border-radius:6px;color:#334155;">
            Admin: ${currentAdminUser ? currentAdminUser.email : 'admin@coherent.test'}
          </span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;">
          ${vendors.map(v => {
            const isApproved = v.approval_status === "approved";
            const isPending = v.approval_status === "pending";
            const isSuspended = v.approval_status === "suspended";
            const statusColor = isApproved ? "#10b981" : (isPending ? "#f59e0b" : "#ef4444");

            return `
              <div style="border:1.5px solid #e2e8f0;border-radius:10px;padding:14px;background:#f8fafc;display:flex;flex-direction:column;justify-content:space-between;gap:10px;">
                <div>
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <strong style="font-size:14px;color:#0f172a;">${v.vendor_name}</strong>
                    <span style="font-size:11px;font-weight:800;padding:2px 8px;border-radius:12px;background:#fff;border:1px solid ${statusColor};color:${statusColor};text-transform:uppercase;">
                      ${v.approval_status}
                    </span>
                  </div>
                  <div style="font-size:11.5px;color:#64748b;margin-top:2px;">Code: <code>${v.vendor_code}</code> • ${v.category || 'Retailer'}</div>
                  <div style="font-size:11.5px;color:#64748b;">Contact: ${v.contact_email || '-'}</div>
                  <div style="font-size:12px;color:#334155;margin-top:6px;font-weight:600;">
                    Stock: ${v.in_stock_count || 0} units • Sold: ${v.sold_count || 0}
                  </div>
                </div>

                <div style="display:flex;gap:6px;margin-top:4px;">
                  ${!isApproved ? `
                    <button onclick="updateVendorStatus(${v.vendor_id}, 'approved')" style="flex:1;padding:6px;background:#10b981;color:#fff;border:none;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;">
                      ✓ Approve
                    </button>
                  ` : ''}
                  ${!isSuspended ? `
                    <button onclick="updateVendorStatus(${v.vendor_id}, 'suspended')" style="flex:1;padding:6px;background:#f59e0b;color:#fff;border:none;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;">
                      ⏸ Suspend
                    </button>
                  ` : `
                    <button onclick="updateVendorStatus(${v.vendor_id}, 'approved')" style="flex:1;padding:6px;background:#10b981;color:#fff;border:none;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;">
                      ▶ Unsuspend
                    </button>
                  `}
                  <button onclick="updateVendorStatus(${v.vendor_id}, 'rejected')" style="padding:6px 10px;background:#ef4444;color:#fff;border:none;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;">
                    ✕
                  </button>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    } catch (e) {
      console.error("Error loading admin vendor approvals:", e);
    }
  }

  window.updateVendorStatus = async function(vendorId, newStatus) {
    if (!confirm(`Are you sure you want to change vendor status to '${newStatus.toUpperCase()}'?`)) {
      return;
    }

    try {
      const res = await fetch(`/api/admin/vendors/${vendorId}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ approval_status: newStatus })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        alert(`Vendor status updated to ${newStatus}.`);
        injectAdminControls();
      } else {
        alert(data.error || "Failed to update vendor status.");
      }
    } catch (err) {
      alert("Network error updating vendor status.");
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    checkAdminAuth();
  });

})();
