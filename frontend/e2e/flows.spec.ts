import { expect, test } from "@playwright/test";

/**
 * Dua alur E2E via browser nyata (Chromium) melawan backend + frontend yang
 * benar-benar berjalan. Urutan penting: alur HR membuat lowongan aktif yang
 * kemudian dilihat kandidat.
 */

const HR = { name: "Dewi Lestari", email: "hr-e2e@demo.talentsync.dev", password: "E2eTest2026!" };
const CAND = { name: "Sarah Wijaya", email: "cand-e2e@demo.talentsync.dev", password: "E2eTest2026!" };
const HR_LOOP = { name: "Ratna Pratiwi", email: "hr-loop-e2e@demo.talentsync.dev", password: "E2eTest2026!" };
const CAND_LOOP = { name: "Budi Santoso", email: "cand-loop-e2e@demo.talentsync.dev", password: "E2eTest2026!" };

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

  // M5 — skill yang TIDAK dimiliki kandidat E2E: memastikan skill gap + saran
  // belajar benar-benar tampil di halaman kompatibilitas kandidat.
  await skillInput.fill("Tableau");
  const tableauOption = page.getByRole("option", { name: "Tableau" }).first();
  await expect(tableauOption).toBeVisible();
  await tableauOption.click();
  const tableauChip = page.locator("li", { hasText: "Tableau" });
  await tableauChip.getByRole("button", { name: "Wajib" }).click(); // toggle → Disarankan
  await expect(tableauChip.getByRole("button", { name: "Disarankan" })).toBeVisible();

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
  // M8 — tombol lamar nyata menggantikan placeholder "Lamar (segera hadir)".
  await expect(page.getByRole("button", { name: "Lamar dengan CV Utama" })).toBeVisible();

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
  const reviewUrl = page.url(); // dipakai ulang pada langkah M7 (diagnosis)
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

  // M4/M5 — Kompatibilitas & skill gap: kembali ke detail lowongan lalu cek kecocokan
  await page.getByRole("link", { name: "Cari Lowongan" }).click();
  const compatJobLink = page.getByRole("link", { name: "Lead Full-Stack Engineer E2E" });
  await expect(compatJobLink).toBeVisible();
  await compatJobLink.click();
  await expect(page.getByRole("heading", { name: "Lead Full-Stack Engineer E2E" })).toBeVisible();

  // M8 — Lamar lowongan dengan CV utama yang sudah dikonfirmasi (cover letter opsional)
  await page.getByRole("button", { name: "Lamar dengan CV Utama" }).click();
  await page
    .getByLabel("Cover letter (opsional)")
    .fill("Saya memiliki pengalaman full-stack yang relevan untuk posisi ini.");
  await page.getByRole("button", { name: "Kirim Lamaran" }).click();
  await expect(page.getByTestId("apply-success-chip")).toBeVisible();

  await page.getByRole("link", { name: "Cek Kompatibilitas" }).click();
  await expect(page).toHaveURL(/\/app\/jobs\/[^/]+\/compatibility/);

  // Komputasi embedding bisa lambat — timeout longgar hanya untuk langkah kompatibilitas.
  const overall = page.getByTestId("compat-overall");
  await expect(overall).toBeVisible({ timeout: 30_000 });
  await expect(overall).not.toHaveText("");

  // Faktor skor, panel penjelasan deterministik, dan bagian skill gap
  await expect(page.getByRole("img", { name: /Skill Coverage:/ }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Mengapa skor ini?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analisis Skill Gap" })).toBeVisible();

  // Minimal satu rekomendasi belajar untuk gap yang ditemukan
  await expect(page.locator("[data-learning-item]").first()).toBeVisible({ timeout: 30_000 });

  // M6 — Rekomendasi lowongan: buka via menu navigasi
  await page.getByRole("link", { name: "Rekomendasi", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/recommendations/);
  await expect(page.getByRole("heading", { name: "Rekomendasi Lowongan" })).toBeVisible();

  // Komputasi embedding saat pertama bisa lambat — timeout longgar.
  const firstRecLink = page.locator("[data-recommendation-link]").first();
  await expect(firstRecLink).toBeVisible({ timeout: 30_000 });
  const recTitle = (await firstRecLink.innerText()).trim();
  await firstRecLink.click();
  await expect(page).toHaveURL(/\/app\/jobs\/[^/]+$/);
  await expect(page.getByRole("heading", { name: recTitle })).toBeVisible();

  // M7 — Diagnosis CV: buka ulang halaman review CV yang dipakai di alur ini
  await page.goto(reviewUrl);
  await expect(page.getByRole("heading", { name: "Diagnosis CV (otomatis)" })).toBeVisible();
  const diagnosisScore = page.getByTestId("diagnosis-score");
  await expect(diagnosisScore).toBeVisible();
  await expect(diagnosisScore).not.toHaveText("");

  // M8 — Lamaran Saya: lamaran yang dikirim di atas tampil dengan status Terkirim
  await page.getByRole("link", { name: "Lamaran", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/applications/);
  await expect(page.getByRole("heading", { name: "Lamaran Saya" })).toBeVisible();
  await expect(page.getByTestId("application-list")).toBeVisible();
  await expect(page.getByRole("link", { name: "Lead Full-Stack Engineer E2E" })).toBeVisible();
  await expect(page.getByTestId("application-status").first()).toHaveText("Terkirim");
});

test("Applications loop: candidate applies → HR reviews → ranking", async ({ page }) => {
  // --- HR segar: perusahaan + lowongan aktif (tes ini mandiri dari dua alur lain) ---
  await page.goto("/register");
  await page.getByRole("button", { name: /Rekruter \/ HR/ }).click();
  await page.getByLabel("Nama Lengkap").fill(HR_LOOP.name);
  await page.getByLabel("Email").fill(HR_LOOP.email);
  await page.locator('input[type="password"]').first().fill(HR_LOOP.password);
  await page.locator('input[type="password"]').nth(1).fill(HR_LOOP.password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Daftar Akun Sekarang" }).click();
  await expect(page).toHaveURL(/\/hr\/company/);
  await page.getByLabel("Nama Perusahaan").fill("PT Loop E2E");
  await page.getByLabel("Industri").fill("Teknologi");
  await page.getByRole("button", { name: "Buat Perusahaan" }).click();
  await expect(page.getByText("Profil perusahaan tersimpan.")).toBeVisible();

  await page.getByRole("link", { name: "Kelola Lowongan" }).click();
  await page.getByRole("link", { name: "+ Buat Lowongan Baru" }).click();
  await page.getByLabel("Nama Posisi Pekerjaan").fill("Loop Flow Engineer E2E");
  await page
    .getByLabel("Deskripsi Pekerjaan")
    .fill("Memvalidasi alur lamaran kandidat hingga ranking kandidat untuk HR.");
  const loopSkillInput = page.getByPlaceholder("Ketik minimal 2 huruf, mis. python…");
  await loopSkillInput.fill("pyt");
  const loopPythonOption = page.getByRole("option", { name: "Python" }).first();
  await expect(loopPythonOption).toBeVisible();
  await loopPythonOption.click();
  await page.getByLabel("Lokasi").fill("Bandung");
  await page.getByRole("button", { name: "Terbitkan Lowongan" }).click();

  // Simpan id lowongan dari URL detail (dipakai ulang untuk halaman pelamar & ranking).
  // Regex UUID agar tidak cocok dengan /hr/jobs/new sebelum navigasi selesai.
  await expect(page).toHaveURL(/\/hr\/jobs\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  const loopJobId = page.url().split("/").pop() as string;
  await expect(page.getByText("Aktif", { exact: true })).toBeVisible();

  // --- Kandidat segar: daftar → CV terkonfirmasi → lamar via UI ---
  await page.getByRole("button", { name: "Keluar" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.goto("/register");
  await page.getByRole("button", { name: "Pencari Kerja" }).click();
  await page.getByLabel("Nama Lengkap").fill(CAND_LOOP.name);
  await page.getByLabel("Email").fill(CAND_LOOP.email);
  await page.locator('input[type="password"]').first().fill(CAND_LOOP.password);
  await page.locator('input[type="password"]').nth(1).fill(CAND_LOOP.password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Daftar Akun Sekarang" }).click();
  await expect(page).toHaveURL(/\/app/);

  // CV utama terkonfirmasi adalah prasyarat apply
  await page.getByRole("link", { name: "CV Saya", exact: true }).click();
  await page.locator("input[type=file]").setInputFiles("e2e/fixtures/sample-cv.pdf");
  await page.getByRole("button", { name: "Unggah CV" }).click();
  const loopReviewLink = page.getByRole("link", { name: "Review ekstraksi" });
  await expect(loopReviewLink).toBeVisible({ timeout: 30_000 });
  await loopReviewLink.click();
  await page.getByPlaceholder("mis. Sarah Wijaya").fill(CAND_LOOP.name);
  await page.getByRole("button", { name: "Simpan & Konfirmasi" }).click();
  await expect(page).toHaveURL(/\/app\/cv$/);
  await expect(page.getByText("Terkonfirmasi", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Cari Lowongan" }).click();
  const loopJobLink = page.getByRole("link", { name: "Loop Flow Engineer E2E" });
  await expect(loopJobLink).toBeVisible();
  await loopJobLink.click();
  await expect(page.getByRole("heading", { name: "Loop Flow Engineer E2E" })).toBeVisible();

  await page.getByRole("button", { name: "Lamar dengan CV Utama" }).click();
  await page
    .getByLabel("Cover letter (opsional)")
    .fill("Saya berminat pada posisi ini dan siap bergabung segera.");
  await page.getByRole("button", { name: "Kirim Lamaran" }).click();
  await expect(page.getByTestId("apply-success-chip")).toBeVisible();

  // --- HR: login ulang → pelamar → ubah status → ranking kandidat ---
  await page.getByRole("button", { name: "Keluar" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("button", { name: /Rekruter \/ HR/ }).click();
  await page.getByLabel("Email").fill(HR_LOOP.email);
  await page.getByLabel("Kata Sandi").fill(HR_LOOP.password);
  await page.getByRole("button", { name: "Masuk ke Akun →" }).click();
  await expect(page).toHaveURL(/\/hr/);

  await page.goto(`/hr/jobs/${loopJobId}/applications`);
  await expect(page.getByRole("heading", { name: "Pelamar" })).toBeVisible();
  const applicantRow = page.locator("tr", { hasText: CAND_LOOP.name });
  await expect(applicantRow).toBeVisible();
  await expect(applicantRow.getByTestId("application-status-chip")).toHaveText("Terkirim");
  await expect(applicantRow.getByText(/siap bergabung segera/)).toBeVisible();

  // PATCH status via select → optimistic update → chip berubah menjadi Ditinjau
  await applicantRow.getByRole("combobox").selectOption("reviewed");
  await expect(applicantRow.getByTestId("application-status-chip")).toHaveText("Ditinjau");

  await page.goto(`/hr/jobs/${loopJobId}/ranking`);
  await expect(page.getByRole("heading", { name: "Ranking Kandidat" })).toBeVisible();
  // Skor komputasi embedding bisa lambat — timeout longgar.
  const rankingScore = page.getByTestId("ranking-score").first();
  await expect(rankingScore).toBeVisible({ timeout: 60_000 });
  await expect(rankingScore).not.toHaveText("—");
  await expect(page.getByTestId("ranking-row").first()).toContainText(CAND_LOOP.name);
});
