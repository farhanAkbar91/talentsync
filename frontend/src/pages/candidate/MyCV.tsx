import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { deleteCv, downloadCv, fetchCvs, setPrimaryCv, uploadCv, type CVDoc } from "../../lib/api";
import { cvStatusLabels, formatDateTime, formatFileSize } from "../../lib/format";
import { Alert, Badge, Button, EmptyState, Spinner } from "../../components/ui";

export default function MyCvPage() {
  const [cvs, setCvs] = useState<CVDoc[] | null>(null);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [selectedFileSize, setSelectedFileSize] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function isBusy(list: CVDoc[]): boolean {
    return list.some(
      (c) =>
        c.status === "pending" ||
        c.status === "processing" ||
        c.extraction_status === "pending",
    );
  }

  async function refresh(): Promise<CVDoc[]> {
    const current = await fetchCvs();
    setCvs(current);
    return current;
  }

  const pollTimer = useRef<number | undefined>(undefined);

  function schedulePoll(current: CVDoc[]) {
    window.clearTimeout(pollTimer.current);
    if (isBusy(current)) {
      pollTimer.current = window.setTimeout(poll, 800);
    }
  }

  async function poll(): Promise<void> {
    try {
      schedulePoll(await refresh());
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal memuat." });
    }
  }

  useEffect(() => {
    poll();
    return () => window.clearTimeout(pollTimer.current);
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFileName(file.name);
      setSelectedFileSize((file.size / (1024 * 1024)).toFixed(2) + " MB");
    } else {
      setSelectedFileName(null);
      setSelectedFileSize(null);
    }
  }

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setMessage({ kind: "error", text: "Pilih berkas PDF terlebih dahulu." });
      return;
    }
    setUploading(true);
    setMessage(null);
    try {
      await uploadCv(file);
      if (fileRef.current) fileRef.current.value = "";
      setSelectedFileName(null);
      setSelectedFileSize(null);
      await poll();
      setMessage({
        kind: "success",
        text: "CV terunggah. Ekstraksi berjalan otomatis — status pada tabel diperbarui sendiri.",
      });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Unggah gagal." });
    } finally {
      setUploading(false);
    }
  }

  async function handlePrimary(cv: CVDoc) {
    try {
      await setPrimaryCv(cv.id);
      await poll();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal." });
    }
  }

  async function handleDelete(cv: CVDoc) {
    if (!window.confirm(`Hapus CV "${cv.original_filename}"? Riwayat versi tetap tersimpan.`)) return;
    try {
      await deleteCv(cv.id);
      await poll();
      setMessage({ kind: "success", text: "CV dihapus (soft delete)." });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal menghapus." });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Page Header - directly starts with page title */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-1 max-w-2xl">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
            CV Saya
          </h1>
          <p className="text-sm text-on-surface-variant leading-relaxed">
            Unggah CV PDF (maks. 10 MB). Berkas disimpan aman dan hanya dapat diakses oleh Anda dan tim perekrut.
          </p>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container-lowest border border-slate-200 text-on-surface-variant text-xs self-start md:self-auto">
          <span className="material-symbols-outlined text-primary text-[18px]">verified_user</span>
          <span>Terenkripsi &amp; Terlindungi</span>
        </div>
      </div>

      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {/* Grid: Main Column (Upload + List) + Guidelines Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Main Column */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {/* Upload Card */}
          <section className="bg-surface-container-lowest rounded-xl border border-slate-200 p-5 sm:p-6">
            <div className="flex items-center justify-between pb-4 mb-4 border-b border-surface-container">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-primary-fixed flex items-center justify-center text-primary">
                  <span className="material-symbols-outlined text-[20px]">upload_file</span>
                </div>
                <div>
                  <h2 className="text-base font-semibold text-on-surface">
                    Formulir Pengunggahan CV
                  </h2>
                  <p className="text-xs text-on-surface-variant">
                    Satu berkas aktif sebagai acuan rekomendasi karir
                  </p>
                </div>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant font-medium">
                Dokumen Utama
              </span>
            </div>

            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                void handleUpload();
              }}
            >
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-on-surface" htmlFor="cv-file-input">
                  Pilih Berkas PDF
                </label>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 p-1.5 bg-surface-container-low rounded-lg border border-slate-200">
                  <label
                    htmlFor="cv-file-input"
                    className="cursor-pointer shrink-0 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-surface-container-lowest text-on-surface text-sm font-medium border border-slate-200 hover:bg-surface-container transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">attachment</span>
                    <span>Choose File</span>
                  </label>
                  <input
                    id="cv-file-input"
                    ref={fileRef}
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <div className="flex items-center justify-between px-3 py-1 flex-1 min-w-0">
                    <span className="text-sm text-on-surface-variant truncate">
                      {selectedFileName || "No file chosen"}
                    </span>
                    {selectedFileSize && (
                      <span className="text-xs px-2 py-0.5 rounded bg-surface-container text-on-surface font-medium">
                        {selectedFileSize}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Constraints Info */}
              <div className="flex items-start gap-2.5 p-3 rounded-lg bg-surface-container-low text-xs border border-slate-200">
                <span className="material-symbols-outlined text-primary text-[18px] shrink-0 mt-0.5">
                  info
                </span>
                <div>
                  <strong className="text-on-surface font-semibold">Ketentuan Berkas: </strong>
                  <span className="text-on-surface-variant">
                    Format PDF, ≤ 10 MB, maks. 20 halaman. CV identik tidak dapat diunggah dua kali.
                  </span>
                </div>
              </div>

              {/* Upload Button */}
              <div className="flex items-center justify-end pt-1">
                <Button type="submit" disabled={uploading}>
                  {uploading ? "Mengunggah…" : "Unggah CV"}
                </Button>
              </div>
            </form>
          </section>

          {/* CV Document Inventory */}
          <section className="bg-surface-container-lowest rounded-xl border border-slate-200 p-5 sm:p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-on-surface">Daftar Dokumen CV</h2>
                <p className="text-xs text-on-surface-variant">
                  Riwayat berkas yang tersimpan di profil Anda
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-surface-container-high text-on-surface text-xs font-semibold">
                Total: {cvs ? cvs.length : 0} Berkas
              </span>
            </div>

            {!cvs ? (
              <Spinner />
            ) : cvs.length === 0 ? (
              <EmptyState
                title="Belum ada CV terunggah"
                description="Unggah CV pertama Anda di atas."
              />
            ) : (
              <div className="overflow-x-auto -mx-5 sm:mx-0">
                <table className="w-full text-left text-sm min-w-[600px]">
                  <thead>
                    <tr className="border-b border-surface-container text-xs uppercase tracking-wider text-secondary font-semibold">
                      <th className="px-4 py-3">Berkas</th>
                      <th className="px-4 py-3">Ukuran</th>
                      <th className="px-4 py-3">Halaman</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Diunggah</th>
                      <th className="px-4 py-3 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high">
                    {cvs.map((cv) => (
                      <tr key={cv.id} className="hover:bg-surface-container-low/50 transition-colors">
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-medium text-on-surface">{cv.original_filename}</span>
                            {cv.version > 1 && (
                              <span
                                title={`Versi ${cv.version} — dihasilkan dari optimasi CV`}
                                className="inline-flex items-center rounded-full bg-primary-fixed px-2 py-0.5 text-[11px] font-semibold text-primary"
                              >
                                v{cv.version}
                              </span>
                            )}
                            {cv.is_primary && (
                              <Badge value="active" label="CV Utama" />
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-secondary text-xs">
                          {formatFileSize(cv.file_size_bytes)}
                        </td>
                        <td className="px-4 py-3.5 text-secondary text-xs">
                          {cv.page_count ?? "—"}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge value={cv.status} label={cvStatusLabels[cv.status]} />
                            {cv.extraction_status === "done" && cv.extraction_confirmed === true && (
                              <Badge value="ready" label="Terkonfirmasi" />
                            )}
                            {cv.extraction_status === "done" && cv.extraction_confirmed === false && (
                              <Badge value="pending" label="Perlu review" />
                            )}
                            {cv.extraction_status === "failed" && cv.status !== "failed" && (
                              <Badge value="failed" label="Gagal" />
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-secondary text-xs">
                          {formatDateTime(cv.created_at)}
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          <div className="flex justify-end items-center gap-1.5 flex-wrap">
                            {cv.extraction_status === "done" && cv.extraction_confirmed !== true && (
                              <Link
                                to={`/app/cv/${cv.id}/review`}
                                className="inline-flex items-center justify-center rounded-lg px-2.5 py-1 text-xs font-semibold text-primary hover:bg-primary-fixed transition-colors"
                              >
                                Review ekstraksi
                              </Link>
                            )}
                            {cv.extraction_confirmed === true && (
                              <Link
                                to={`/app/cv/${cv.id}/skills`}
                                className="inline-flex items-center justify-center rounded-lg px-2.5 py-1 text-xs font-semibold text-primary hover:bg-primary-fixed transition-colors"
                              >
                                Skills terstandardisasi
                              </Link>
                            )}
                            {!cv.is_primary && cv.status !== "failed" && (
                              <button
                                type="button"
                                onClick={() => void handlePrimary(cv)}
                                className="px-2.5 py-1 rounded-lg text-xs font-medium text-secondary hover:text-on-surface hover:bg-surface-container transition-colors"
                              >
                                Jadikan Utama
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => void downloadCv(cv.id, cv.original_filename)}
                              className="px-2 py-1 rounded-lg text-xs font-medium text-secondary hover:text-on-surface hover:bg-surface-container transition-colors"
                            >
                              Unduh
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDelete(cv)}
                              className="px-2 py-1 rounded-lg text-xs font-medium text-error hover:bg-error-container/40 transition-colors"
                            >
                              Hapus
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        {/* Sidebar Column */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Optimal Extraction Guidelines */}
          <section className="bg-surface-container-lowest rounded-xl border border-slate-200 p-5 sm:p-6 flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-primary">
                <span className="material-symbols-outlined text-[20px]">lightbulb</span>
              </div>
              <h3 className="text-base font-semibold text-on-surface">Panduan Ekstraksi Optimal</h3>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Algoritma pemindaian bekerja maksimal jika resume Anda memenuhi standar keterbacaan data berikut:
            </p>
            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 rounded-lg bg-surface-container-low border border-slate-200">
                <div className="w-5 h-5 rounded-full bg-primary-fixed text-primary flex items-center justify-center shrink-0 text-xs font-bold mt-0.5">
                  1
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-on-surface">Teks Standar</h4>
                  <p className="text-xs text-on-surface-variant">Gunakan teks standar (bukan gambar scan).</p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 rounded-lg bg-surface-container-low border border-slate-200">
                <div className="w-5 h-5 rounded-full bg-primary-fixed text-primary flex items-center justify-center shrink-0 text-xs font-bold mt-0.5">
                  2
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-on-surface">Struktur Berurutan</h4>
                  <p className="text-xs text-on-surface-variant">
                    Cantumkan riwayat pengalaman, pendidikan, dan keahlian teknis secara berurutan.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 rounded-lg bg-surface-container-low border border-slate-200">
                <div className="w-5 h-5 rounded-full bg-primary-fixed text-primary flex items-center justify-center shrink-0 text-xs font-bold mt-0.5">
                  3
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-on-surface">Format Asli PDF</h4>
                  <p className="text-xs text-on-surface-variant">Pastikan format file adalah PDF asli.</p>
                </div>
              </div>
            </div>

            <div className="p-3 bg-surface-container-low rounded-lg flex flex-col gap-1.5 border border-slate-200">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-on-surface-variant uppercase tracking-wider text-[11px]">
                  Akurasi Ekstraksi PDF Asli
                </span>
                <span className="font-bold text-tertiary">99.4%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden">
                <div className="h-full bg-primary-container rounded-full" style={{ width: "99.4%" }} />
              </div>
              <p className="text-[11px] text-on-surface-variant pt-0.5">
                Format non-scan diekstrak 10x lebih cepat oleh sistem penyelarasan lowongan.
              </p>
            </div>
          </section>

          {/* Privacy & Protection Box */}
          <div className="bg-surface-container-lowest rounded-xl border border-slate-200 p-4 sm:p-5 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary shrink-0">
              <span className="material-symbols-outlined text-[22px]">lock</span>
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-on-surface">Privasi Terjamin</h4>
              <p className="text-xs text-on-surface-variant leading-snug">
                Hanya tim perekrut pada lowongan yang Anda lamar yang dapat melihat isi dokumen ini.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
