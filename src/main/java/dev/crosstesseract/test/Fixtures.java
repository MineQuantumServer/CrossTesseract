package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.BusinessIds;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.runtime.RuntimeService;
import java.util.UUID;
import java.util.function.Consumer;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTestHelper;

/** Real backend fixture: tests use trusted synthetic console UUIDs, never a client-supplied owner. */
public final class Fixtures {
    public static void bound(GameTestHelper helper,Consumer<TesseractBlockEntity> test){
        var runtime=RuntimeService.get(helper.getLevel().getServer());UUID owner=BusinessIds.next();var device=new TesseractBlockEntity[1];
        helper.startSequence().thenWaitUntil(()->helper.assertTrue(runtime!=null && runtime.online(),"real test backend must be online"))
            .thenExecute(()->{helper.setBlock(new BlockPos(1,1,1),CrossTesseract.TESSERACT.get());device[0]=(TesseractBlockEntity)helper.getBlockEntity(new BlockPos(1,1,1));device[0].placed(owner);})
            .thenWaitUntil(()->helper.assertTrue(device[0].registered(),"endpoint registration pending"))
            .thenExecute(()->runtime.submit(a->a.createChannel(owner,"GameTest_"+BusinessIds.next().toString().substring(28,36),BusinessIds.next()),channel->runtime.bindEndpoint(device[0],owner,device[0].endpointVersion(),channel,x->{},code->helper.assertTrue(false,code)),code->helper.assertTrue(false,code)))
            .thenWaitUntil(()->helper.assertTrue(device[0].channel()!=null && device[0].pauseReason().isEmpty() && device[0].channelOwner()!=null,"permission refresh pending"))
            .thenExecute(()->test.accept(device[0]));
    }
    private Fixtures(){}
}
