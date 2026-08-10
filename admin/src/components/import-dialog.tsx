"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Upload, FileSpreadsheet, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

interface ImportRow {
  row_number: number;
  name: string;
  description: string;
  category: string;
  price: number;
  recognized: boolean;
}

interface PreviewResponse {
  source: string;
  total_rows: number;
  recognized_rows: number;
  rows: ImportRow[];
  unmapped_columns: string[];
  truncated?: boolean;
}

interface ConfirmResponse {
  created: number;
  category_id: number;
  stock_template_url?: string;
}

const SOURCE_LABELS: Record<string, string> = {
  ozon: "Ozon",
  wb: "Wildberries",
  ym: "Яндекс.Маркет",
};

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}

export function ImportDialog({ open, onOpenChange, onImported }: ImportDialogProps) {
  const [source, setSource] = useState("wb");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);

  function reset() {
    setFile(null);
    setPreview(null);
    setSelected(new Set());
    setLoading(false);
    setImporting(false);
  }

  async function handlePreview() {
    if (!file) {
      toast.error("Выберите файл");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const data = await api.post<PreviewResponse>(
        `/catalog/import/preview?source=${source}`,
        formData,
        120000,
      );
      setPreview(data);
      const initSelected = new Set<number>();
      data.rows.forEach((r) => {
        if (r.recognized) initSelected.add(r.row_number);
      });
      setSelected(initSelected);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка парсинга файла");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    if (selected.size === 0) {
      toast.error("Выберите хотя бы один товар");
      return;
    }

    const rows = preview!.rows
      .filter((r) => selected.has(r.row_number))
      .map((r) => ({
        name: r.name,
        description: r.description,
        category: r.category,
        price: r.price,
      }));

    setImporting(true);
    try {
      const result = await api.post<ConfirmResponse>("/catalog/import/confirm", { rows });
      toast.success(
        `Импортировано товаров: ${result.created}. Заполните остатки и характеристики перед публикацией.`,
      );
      if (result.stock_template_url) {
        toast.info("Скачайте шаблон остатков на странице товаров (кнопка «Остатки»)");
      }
      onImported();
      reset();
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка импорта");
    } finally {
      setImporting(false);
    }
  }

  function toggleRow(rowNumber: number) {
    const next = new Set(selected);
    if (next.has(rowNumber)) {
      next.delete(rowNumber);
    } else {
      next.add(rowNumber);
    }
    setSelected(next);
  }

  function toggleAll() {
    if (preview && selected.size === preview.rows.filter((r) => r.recognized).length) {
      setSelected(new Set());
    } else if (preview) {
      setSelected(new Set(preview.rows.filter((r) => r.recognized).map((r) => r.row_number)));
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
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            Импорт товаров
          </DialogTitle>
          <DialogDescription>
            Загрузите выгрузку из маркетплейса (.xlsx). Названия, описания и цены импортируются автоматически.
            Остатки, характеристики и фото нужно заполнить вручную.
          </DialogDescription>
        </DialogHeader>

        {!preview ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Маркетплейс</Label>
              <Select value={source} onValueChange={(v) => setSource(v || "wb")}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ozon">Ozon</SelectItem>
                  <SelectItem value="wb">Wildberries</SelectItem>
                  <SelectItem value="ym">Яндекс.Маркет</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Файл .xlsx</Label>
              <div className="flex items-center gap-2">
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
                />
              </div>
              {file && (
                <p className="text-xs text-muted-foreground">
                  Выбран: {file.name} ({(file.size / 1024).toFixed(0)} КБ)
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">
                {SOURCE_LABELS[preview.source] ?? preview.source}
              </Badge>
              <span className="text-sm text-muted-foreground">
                Распознано: {preview.recognized_rows} из {preview.total_rows}
              </span>
              {preview.truncated && (
                <Badge variant="outline" className="text-amber-600">
                  Показаны первые {preview.rows.length} строк
                </Badge>
              )}
            </div>

            <div className="max-h-[300px] overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8">
                      <input
                        type="checkbox"
                        checked={
                          preview.rows.filter((r) => r.recognized).length > 0 &&
                          selected.size === preview.rows.filter((r) => r.recognized).length
                        }
                        onChange={toggleAll}
                        className="h-4 w-4"
                      />
                    </TableHead>
                    <TableHead>Название</TableHead>
                    <TableHead>Категория</TableHead>
                    <TableHead className="text-right">Цена</TableHead>
                    <TableHead className="max-w-[200px]">Описание</TableHead>
                    <TableHead className="w-8"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.map((row) => (
                    <TableRow key={row.row_number} className={row.recognized ? "" : "opacity-50"}>
                      <TableCell>
                        <input
                          type="checkbox"
                          checked={selected.has(row.row_number)}
                          onChange={() => toggleRow(row.row_number)}
                          disabled={!row.recognized}
                          className="h-4 w-4"
                        />
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate" title={row.name}>
                        {row.name || "—"}
                      </TableCell>
                      <TableCell className="max-w-[120px] truncate text-muted-foreground" title={row.category}>
                        {row.category || "—"}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {row.price ? row.price.toLocaleString("ru-RU") + " ₽" : "—"}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-muted-foreground" title={row.description}>
                        {row.description || "—"}
                      </TableCell>
                      <TableCell>
                        {row.recognized ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-500" />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-xs text-muted-foreground">
              Выбрано: {selected.size} из {preview.recognized_rows}
            </p>
          </div>
        )}

        <DialogFooter>
          {preview ? (
            <>
              <Button
                variant="outline"
                onClick={() => { setPreview(null); setSelected(new Set()); }}
                disabled={importing}
              >
                Назад
              </Button>
              <Button onClick={handleConfirm} disabled={importing || selected.size === 0}>
                {importing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Импорт...
                  </>
                ) : (
                  `Импортировать (${selected.size})`
                )}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Отмена
              </Button>
              <Button onClick={handlePreview} disabled={loading || !file}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Парсинг...
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" />
                    Загрузить
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
