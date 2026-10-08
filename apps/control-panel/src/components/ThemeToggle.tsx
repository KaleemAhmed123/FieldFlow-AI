import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <Tip label={`Switch to ${next} theme`}>
      <Button variant="ghost" size="icon" onClick={toggle} aria-label={`Switch to ${next} theme`}>
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </Button>
    </Tip>
  );
}
