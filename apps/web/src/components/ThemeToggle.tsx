"use client";

import * as React from "react";
import { Moon, Sun, Laptop } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
    const { setTheme, theme } = useTheme();

    return (
        <div className="flex items-center gap-1 rounded-md border border-input bg-background p-1">
            <Button
                variant={theme === "light" ? "secondary" : "ghost"}
                size="icon"
                className="h-7 w-7 rounded-sm"
                onClick={() => setTheme("light")}
                title="Light Mode"
            >
                <Sun className="h-[1.2rem] w-[1.2rem]" />
                <span className="sr-only">Light Mode</span>
            </Button>
            <Button
                variant={theme === "system" ? "secondary" : "ghost"}
                size="icon"
                className="h-7 w-7 rounded-sm"
                onClick={() => setTheme("system")}
                title="System (Adaptive)"
            >
                <Laptop className="h-[1.2rem] w-[1.2rem]" />
                <span className="sr-only">System Mode</span>
            </Button>
            <Button
                variant={theme === "dark" ? "secondary" : "ghost"}
                size="icon"
                className="h-7 w-7 rounded-sm"
                onClick={() => setTheme("dark")}
                title="Dark Mode"
            >
                <Moon className="h-[1.2rem] w-[1.2rem]" />
                <span className="sr-only">Dark Mode</span>
            </Button>
        </div>
    );
}
