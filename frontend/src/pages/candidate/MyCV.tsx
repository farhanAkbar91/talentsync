import { useEffect, useRef, useState } from "react";
import { deleteCv, downloadCv, fetchCvs, setPrimaryCv, uploadCv, type CVDoc } from "../../lib/api";
import { cvStatusLabels, formatDateTime, formatFileSize } from "../../lib/format";
import { Alert, Badge, Button, Card, EmptyState, Spinner } from "../../components/ui";

export default function MyCvPage() {
  const [cvs, setCvs] = useState<CVDoc[] | null>(null);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setCvs(await fetchCvs());
  }

  useEffect(() => {
    refresh().catch((err) => setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal memuat." }));
  }, []);

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
      await refresh();
      setMessage({
        kind: "success",
        text: "CV terunggah. Teks dasar sudah diekstrak — analisis AI penuh berjalan pada fase berikutnya.",
      });
      // Ekstraksi berjalan async di server — poll ringan sampai selesai.
      for (let i = 0; i < 10; i++) {
        const current = await fetchCvs();
        setCvs(current);
        if (current.every((c) => c.status !== "pending" && c.status !== "processing")) break;
        await new Promise((resolve) => setTimeout(resolve, 700));
      }
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Unggah gagal." });
    } finally {
      setUploading(false);
    }
  }

  async function handlePrimary(cv: CVDoc) {
    try {
      await setPrimaryCv(cv.id);
      await refresh();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal." });
    }
  }

  async function handleDelete(cv: CVDoc) {
    if (!window.confirm(`Hapus CV "${cv.original_filename}"? Riwayat versi tetap tersimpan.`)) return;
    try {
      await deleteCv(cv.id);
      await refresh();
      setMessage({ kind: "success", text: "CV dihapus (soft delete)." });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal menghapus." });
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">CV Saya</h1>
        <p className="mt-1 text-sm text-slate-500">
          Unggah CV PDF (maks. 10 MB). Berkas disimpan aman dan hanya dapat diakses oleh Anda.
        </p>
      </div>

      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,application/pdf"
            className="text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-primary-50 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-primary-700 hover:file:bg-primary-100"
          />
          <Button onClick={handleUpload} disabled={uploading}>
            {uploading ? "Mengunggah…" : "Unggah CV"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Format PDF, ≤ 10 MB, maks. 20 halaman. CV identik tidak dapat diunggah dua kali.
        </p>
      </Card>

      {!cvs ? (
        <Spinner />
      ) : cvs.length === 0 ? (
        <EmptyState title="Belum ada CV terunggah" description="Unggah CV pertama Anda di atas." />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Berkas</th>
                <th className="px-4 py-3">Ukuran</th>
                <th className="px-4 py-3">Halaman</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Diunggah</th>
                <th className="px-4 py-3 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {cvs.map((cv) => (
                <tr key={cv.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-700">{cv.original_filename}</span>
                    {cv.is_primary && (
                      <Badge value="active" label="CV Utama" />
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{formatFileSize(cv.file_size_bytes)}</td>
                  <td className="px-4 py-3 text-slate-500">{cv.page_count ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge value={cv.status} label={cvStatusLabels[cv.status]} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">{formatDateTime(cv.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      {!cv.is_primary && cv.status !== "failed" && (
                        <Button variant="secondary" onClick={() => handlePrimary(cv)}>
                          Jadikan Utama
                        </Button>
                      )}
                      <Button variant="ghost" onClick={() => downloadCv(cv.id, cv.original_filename)}>
                        Unduh
                      </Button>
                      <Button variant="danger" onClick={() => handleDelete(cv)}>
                        Hapus
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
