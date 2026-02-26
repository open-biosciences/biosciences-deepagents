"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { SubAgent } from "@/app/types/types";

interface SubAgentIndicatorProps {
  subAgent: SubAgent;
  onClick: () => void;
  isExpanded?: boolean;
}

export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent, onClick, isExpanded = true }) => {
    const getStatusIcon = (status: SubAgent["status"]) => {
      switch (status) {
        case "completed":
          return <span className="flex items-center gap-1.5 text-xs text-green-600"><div className="size-2 rounded-full bg-green-600" />Done</span>;
        case "active":
        case "pending":
          return <span className="flex items-center gap-1.5 text-xs text-blue-600"><div className="size-2 rounded-full bg-blue-600 animate-pulse" />Running</span>;
        case "error":
          return <span className="flex items-center gap-1.5 text-xs text-red-600"><div className="size-2 rounded-full bg-red-600" />Error</span>;
        default:
          return null;
      }
    };

    return (
      <div className="w-fit max-w-[70vw] overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClick}
          className="flex w-full items-center justify-between gap-4 border-none px-4 py-2 text-left shadow-none outline-none transition-colors duration-200"
        >
          <div className="flex w-full items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="font-sans text-[15px] font-bold leading-[140%] tracking-[-0.6px] text-[#3F3F46]">
                {subAgent.subAgentName}
              </span>
              {getStatusIcon(subAgent.status)}
            </div>
            {isExpanded ? (
              <ChevronUp
                size={14}
                className="shrink-0 text-[#70707B]"
              />
            ) : (
              <ChevronDown
                size={14}
                className="shrink-0 text-[#70707B]"
              />
            )}
          </div>
        </Button>
      </div>
    );
  }
);

SubAgentIndicator.displayName = "SubAgentIndicator";
