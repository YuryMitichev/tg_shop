"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Download, Upload, Loader2, FileSpreadsheet } from "lucide-react";

interface StockUpdateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdated: () => void;
}

export function StockUpdateDialog({ open, onOpenChange, onUpdated }: StockUpdateDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [uploading, setUploading] = useState(false);

  function reset() {
    setFile(null);
    setDownloading(false);
    setUploading(false);
  }

  async function handleDownloadTemplate() {
    setDownloading(true);
    try {
      const resp = await fetch(`${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"}/api/admin/catalog/stock-template`, {
        credentials: "include",
      });
      if (!resp.ok) throw new Error("Ошибка скачивания шаблона");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "stock_template.xlsx";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setDownloading(false);
    }
  }

  async function handleUpload() {
    if (!file) {
      toast.error("Выберите файл");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api.post<{ updated: number; not_found: number }>(
        "/catalog/stock/bulk-update",
        formData,
        120000,
      );
      const parts: string[] = [`Обновлено: ${result.updated}`];
      if (result.not_found > 0) {
        parts.push(`не найдено: ${result.not_found}`);
      }
      toast.success(parts.join(", "));
      onUpdated();
      reset();
      onOpenChange(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Ошибка";
      if (msg.startsWith("[")) {
        try {
          const errors = JSON.parse(msg);
          toast.error(errors.join("; "));
        } catch {
          toast.error(msg);
        }
      } else {
        toast.error(msg);
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            Обновление остатков
          </DialogTitle>
          <DialogDescription>
            Скачайте шаблон, заполните колонку «Остаток» и загрузите обратно.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Шаг 1. Скачать шаблон</Label>
            <Button
              variant="outline"
              onClick={handleDownloadTemplate}
              disabled={downloading}
              className="w-full"
            >
              {downloading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Скачивание...</>
              ) : (
                <><Download className="mr-2 h-4 w-4" /> Скачать шаблон (.xlsx)</>
              )}
            </Button>
            <p className="text-xs text-muted-foreground">
              Шаблон содержит все товары и варианты. Колонка «id» — техническая, не изменяйте её.
            </p>
          </div>

          <div className="space-y-2">
            <Label>Шаг 2. Загрузить заполненный файл</Label>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
            />
            {file && (
              <p className="text-xs text-muted-foreground">
                Выбран: {file.name} ({(file.size / 1024).toFixed(0)} КБ)
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={uploading}>
            Отмена
          </Button>
          <Button onClick={handleUpload} disabled={uploading || !file}>
            {uploading ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Обновление...</>
            ) : (
              <><Upload className="mr-2 h-4 w-4" /> Обновить остатки</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
