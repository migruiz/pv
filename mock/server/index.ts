import express from "express";
import cors from "cors";
import { router } from "./routes.js";

const PORT = 3002;
const app = express();

app.use(cors());
app.use(router);

app.listen(PORT, () => {
  console.log(`Mock solar simulator running on http://localhost:${PORT}`);
});
