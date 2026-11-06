import { expect, test } from "@playwright/test";

/**
 * Dua alur E2E via browser nyata (Chromium) melawan backend + frontend yang
 * benar-benar berjalan. Urutan penting: alur HR membuat lowongan aktif yang
 * kemudian dilihat kandidat.
 */

const HR = { name: "Dewi Lestari", email: "hr-e2e@demo.talentsync.dev", password: "E2eTest2026!" };
const CAND = { name: "Sarah Wijaya", email: "cand-e2e@demo.talentsync.dev", password: "E2eTest2026!" };

test("HR flow: register → company → create job → publish → edit → close second job", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByRole("button", { name: /Rekruter \/ HR/ }).click();
  await page.getByLabel("Nama Lengkap").fill(HR.name);
  await page.getByLabel("Email").fill(HR.email);
  await page.locator('input[type="password"]').first().fill(HR.password);
  await page.locator('input[type="password"]').nth(1).fill(HR.password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Daftar Akun Sekarang" }).click();

  // Diarahkan ke profil perusahaan
  await expect(page).toHaveURL(/\/hr\/company/);
  await page.getByLabel("Nama Perusahaan").fill("PT E2E Maju");
  await page.getByLabel("Industri").fill("Teknologi");
  await page.getByRole("button", { name: "Buat Perusahaan" }).click();
  await expect(page.getByText("Profil perusahaan tersimpan.")).toBeVisible();

  // Buat lowongan #1 → terbitkan (tetap aktif untuk alur kandidat)
  await page.getByRole("link", { name: "Kelola Lowongan" }).click();
  await page.getByRole("link", { name: "+ Buat Lowongan Baru" }).click();
  await page.getByLabel("Nama Posisi Pekerjaan").fill("Senior Full-Stack Engineer E2E");
  await page
    .getByLabel("Deskripsi Pekerjaan")
    .fill("Membangun aplikasi web end-to-end bersama tim produk untuk pengujian E2E.");

  // M2 — input skill berupa combobox autocomplete ke kamus standar.
  const skillInput = page.getByPlaceholder("Ketik minimal 2 huruf, mis. python…");
  await skillInput.fill("React.js");
  await skillInput.press("Enter"); // fallback teks bebas → chip "tidak dikenal"
  await expect(page.locator("li", { hasText: "React.js" })).toBeVisible();

  // Autocomplete kamus: ketik "pyt" → pilih "Python" dari dropdown.
  await skillInput.fill("pyt");
  const pythonOption = page.getByRole("option", { name: "Python" }).first();
  await expect(pythonOption).toBeVisible();
  await pythonOption.click();
  const pythonChip = page.locator("li", { hasText: "Python" });
  await expect(pythonChip).toBeVisible();
  await expect(pythonChip.getByRole("button", { name: "Wajib" })).toBeVisible(); // default Wajib

  await skillInput.fill("Docker");
  await skillInput.press("Enter");
  const dockerChip = page.locator("li", { hasText: "Docker" });
  await dockerChip.getByRole("button", { name: "Wajib" }).click();
  await expect(dockerChip.getByRole("button", { name: "Disarankan" })).toBeVisible();

  await page.getByLabel("Lokasi").fill("Jakarta Selatan");
  await page.getByRole("button", { name: "Terbitkan Lowongan" }).click();

  await expect(page).toHaveURL(/\/hr\/jobs\//);
  await expect(page.getByText("Aktif", { exact: true })).toBeVisible();

  // M2 — kartu pemetaan skill ke kamus standar pada detail lowongan HR
  await expect(
    page.getByRole("heading", { name: "Pemetaan skill (kamus standar)" }),
  ).toBeVisible();
  await expect(page.getByText("Python", { exact: true }).first()).toBeVisible();

  // Edit lowongan aktif
  await page.getByRole("link", { name: "Edit" }).click();
  await page.getByLabel("Nama Posisi Pekerjaan").fill("Lead Full-Stack Engineer E2E");
  await page.getByRole("button", { name: "Simpan Perubahan" }).click();
  await expect(page.getByRole("heading", { name: "Lead Full-Stack Engineer E2E" })).toBeVisible();

  // Buat lowongan #2 → terbitkan → tutup (validasi lifecycle close)
  await page.getByRole("link", { name: "Kelola Lowongan" }).click();
  await page.getByRole("link", { name: "+ Buat Lowongan Baru" }).click();
  await page.getByLabel("Nama Posisi Pekerjaan").fill("QA Automation Lead E2E");
  await page
    .getByLabel("Deskripsi Pekerjaan")
    .fill("Menjamin kualitas rilis melalui otomasi pengujian end-to-end.");
  const req2 = page.getByPlaceholder("Ketik minimal 2 huruf, mis. python…");
  await req2.fill("Playwright");
  await req2.press("Enter");
  await page.getByRole("button", { name: "Terbitkan Lowongan" }).click();
  await expect(page.getByText("Aktif", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Tutup", exact: true }).click();
  await expect(page.getByText("Ditutup", { exact: true })).toBeVisible();

  // Katalog publik (anonim): hanya lowongan aktif — lowongan yang ditutup tidak muncul
  const catalog = await page.request.get("http://localhost:5173/api/v1/jobs");
  expect(catalog.ok()).toBeTruthy();
  const body = (await catalog.json()) as { total: number; items: { title: string }[] };
  const titles = body.items.map((item) => item.title);
  expect(titles).toContain("Lead Full-Stack Engineer E2E");
  expect(titles).not.toContain("QA Automation Lead E2E");
});

test("Candidate flow: register → profile → browse → detail → upload CV → review ekstraksi", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByRole("button", { name: "Pencari Kerja" }).click();
  await page.getByLabel("Nama Lengkap").fill(CAND.name);
  await page.getByLabel("Email").fill(CAND.email);
  await page.locator('input[type="password"]').first().fill(CAND.password);
  await page.locator('input[type="password"]').nth(1).fill(CAND.password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Daftar Akun Sekarang" }).click();

  await expect(page).toHaveURL(/\/app/);
  await expect(page.getByRole("heading", { name: /Selamat Datang, Sarah/ })).toBeVisible();

  // Perbarui profil
  await page.getByRole("link", { name: "Profil", exact: true }).click();
  await page.getByLabel("Headline").fill("Senior Full-Stack Engineer");
  const skills = page.getByPlaceholder("mis. React, Python…");
  await skills.fill("React");
  await skills.press("Enter");
  await skills.fill("Python");
  await skills.press("Enter");
  await page.getByRole("button", { name: "Simpan Profil" }).click();
  await expect(page.getByText("Profil berhasil disimpan.")).toBeVisible();

  // Browse jobs → lowongan aktif dari alur HR terlihat
  await page.getByRole("link", { name: "Cari Lowongan" }).click();
  const jobLink = page.getByRole("link", { name: "Lead Full-Stack Engineer E2E" });
  await expect(jobLink).toBeVisible();
  await jobLink.click();
  await expect(page.getByRole("heading", { name: "Lead Full-Stack Engineer E2E" })).toBeVisible();
  await expect(page.getByText("React.js", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Lamar \(segera hadir\)/ })).toBeDisabled();

  // Upload CV
  await page.getByRole("link", { name: "CV Saya", exact: true }).click();
  await page.locator("input[type=file]").setInputFiles("e2e/fixtures/sample-cv.pdf");
  await page.getByRole("button", { name: "Unggah CV" }).click();
  await expect(page.getByText("CV Utama")).toBeVisible();
  await expect(page.getByText("sample-cv.pdf")).toBeVisible();
  await expect(page.getByText("Siap", { exact: true })).toBeVisible({ timeout: 20_000 });

  // M1 — Review ekstraksi: buka halaman review untuk CV yang sudah selesai diekstraksi
  const reviewLink = page.getByRole("link", { name: "Review ekstraksi" });
  await expect(reviewLink).toBeVisible({ timeout: 20_000 });
  await reviewLink.click();
  await expect(page).toHaveURL(/\/app\/cv\/[^/]+\/review/);
  await expect(page.getByRole("heading", { name: "Kontak" })).toBeVisible();

  // Parser heuristik belum tentu mengekstrak nama — nama wajib sebelum konfirmasi.
  await page.getByPlaceholder("mis. Sarah Wijaya").fill("Sarah Wijaya");
  await page.getByRole("button", { name: "Simpan & Konfirmasi" }).click();

  // Kembali ke daftar CV dan chip status berubah menjadi terkonfirmasi
  await expect(page).toHaveURL(/\/app\/cv$/);
  await expect(page.getByText("Terkonfirmasi", { exact: true })).toBeVisible();

  // M2 — Skills terstandardisasi: buka halaman skill hasil pemetaan kamus
  const skillsLink = page.getByRole("link", { name: "Skills terstandardisasi" });
  await expect(skillsLink).toBeVisible();
  await skillsLink.click();
  await expect(page).toHaveURL(/\/app\/cv\/[^/]+\/skills/);
  await expect(page.getByRole("heading", { name: "Skills terstandardisasi" })).toBeVisible();

  const firstSkillName = page.locator("[data-skill-name]").first();
  await expect(firstSkillName).toBeVisible({ timeout: 20_000 });
  const skillName = (await firstSkillName.innerText()).trim();

  // Pastikan minimal satu skill terpilih sebelum menerapkan
  if ((await page.locator("input[type=checkbox]:checked").count()) === 0) {
    await page.locator("input[type=checkbox]:not([disabled])").first().check();
  }
  await page.getByRole("button", { name: "Terapkan ke Profil" }).click();
  await expect(page.getByText(/skill diterapkan ke profil/)).toBeVisible({ timeout: 20_000 });

  await page.getByRole("link", { name: "Lihat profil" }).click();
  await expect(page).toHaveURL(/\/app\/profile/);
  await expect(page.getByText("Skill terstandardisasi (dari CV)")).toBeVisible();
  await expect(page.getByText(skillName, { exact: true }).first()).toBeVisible();
});
