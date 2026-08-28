import { AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Journal } from "@/types";

const statusConfig = {
  healthy: { label: "Yangilanib turadi", icon: CheckCircle2, variant: "success" as const },
  warning: { label: "Tekshirilmoqda", icon: AlertTriangle, variant: "warning" as const },
  missing: { label: "Qo‘lda kiritilgan", icon: WifiOff, variant: "secondary" as const },
};

export function HarvestStatus({ status }: { status: Journal["oaiStatus"] }) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className="gap-1 font-normal">
      <Icon />
      {config.label}
    </Badge>
  );
}
