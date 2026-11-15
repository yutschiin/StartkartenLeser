import { AppBar, Box, Button, Container, Toolbar, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import type { ReactNode } from "react";

interface PageLayoutProps {
  title: string;
  showBrand?: boolean;
  back?: { label: string; onClick: () => void; id?: string; disabled?: boolean };
  chips?: ReactNode;
  actions?: ReactNode;
  singleLine?: boolean;
  children: ReactNode;
}

export function PageLayout({ title, showBrand, back, chips, actions, singleLine, children }: PageLayoutProps) {
  return (
    <>
      <AppBar position="sticky" color="inherit" elevation={0} className="topbar">
        <Toolbar className={`toolbar${singleLine ? " toolbar-single-line" : ""}`}>
          <Box className="page-title">
            {showBrand && <Box className="brand-mark" aria-hidden="true">SL</Box>}
            <Typography variant="h1" component="h1">{title}</Typography>
          </Box>
          {chips && <Box className="header-chips">{chips}</Box>}
          {actions && <Box className="header-actions">{actions}</Box>}
        </Toolbar>
      </AppBar>
      {back && (
        <Box className="sub-header">
          <Button id={back.id} startIcon={<ArrowBackIcon />} onClick={back.onClick} disabled={back.disabled}>
            {back.label}
          </Button>
        </Box>
      )}
      <Container component="main" maxWidth="xl" className="main-container">
        {children}
      </Container>
    </>
  );
}
