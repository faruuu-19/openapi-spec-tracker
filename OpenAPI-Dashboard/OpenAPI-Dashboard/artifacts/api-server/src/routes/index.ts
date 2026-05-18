import { Router, type IRouter } from "express";
import crawlerRouter from "./crawler";
import healthRouter from "./health";

const router: IRouter = Router();

router.use(healthRouter);
router.use(crawlerRouter);

export default router;
